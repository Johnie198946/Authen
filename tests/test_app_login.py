import asyncio
import concurrent.futures
import shutil
import socket
import subprocess
import time
from types import SimpleNamespace

import pytest
import redis
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import services.auth.main as auth
from shared.models.user import Base, User
from shared.middleware.api_logger import filter_sensitive_data
from shared.utils.jwt import create_access_token, create_refresh_token, decode_token, human_principal_claims


@pytest.fixture
def environment(tmp_path, monkeypatch):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    executable = shutil.which('redis-server')
    assert executable, 'Real Redis is required to verify Lua atomicity'
    process = subprocess.Popen([executable, '--bind', '127.0.0.1', '--port', str(port),
        '--save', '', '--appendonly', 'no', '--dir', str(tmp_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    cache = redis.Redis(host='127.0.0.1', port=port, decode_responses=True)
    try:
        for _ in range(100):
            try:
                if cache.ping(): break
            except redis.ConnectionError: time.sleep(.02)
        assert cache.ping()
        monkeypatch.setattr(auth, 'get_redis', lambda: cache)
        engine = create_engine(f'sqlite:///{tmp_path / "auth.db"}', connect_args={'check_same_thread': False})
        Base.metadata.create_all(engine)
        sessions = sessionmaker(bind=engine)
        db = sessions()
        user = User(username='app-login-test', phone='+8619900000000', status='active', password_changed=True)
        other = User(username='app-login-other', phone='+8619900000001', status='active')
        db.add_all([user, other]); db.commit()
        monkeypatch.setattr(auth, 'create_sso_session', lambda *_: SimpleNamespace(session_token='isolated-sso-session'))
        yield cache, db, user, other, sessions
        db.close(); engine.dispose()
    finally:
        cache.close(); process.terminate(); process.wait(timeout=5)


def call(function, *args, **kwargs):
    return asyncio.run(function(*args, **kwargs))


def start(env):
    cache, db, user, *_ = env
    cache.delete('app_login_rate:' + auth.app_login_hash(user.phone))
    started = call(auth.app_login_start, auth.AppLoginStart(phone='19900000000'), db)
    item = call(auth.app_login_pending, user)['items'][0]
    return started, item


def test_real_redis_login_identity_and_one_time_ticket(environment):
    cache, db, user, other, _ = environment
    started, item = start(environment)
    assert len(item['code']) == 6 and item['code'].isascii() and item['code'].isdigit()
    assert call(auth.app_login_pending, other)['items'] == []
    with pytest.raises(HTTPException) as denied:
        call(auth.app_login_confirm, item['id'], auth.AppLoginCode(code=item['code']), other)
    assert denied.value.status_code == 409
    wrong = '000000' if item['code'] != '000000' else '111111'
    with pytest.raises(HTTPException) as denied:
        call(auth.app_login_confirm, item['id'], auth.AppLoginCode(code=wrong), user)
    assert denied.value.status_code == 403
    claims = {'sub': str(user.id), **human_principal_claims('sms')}
    assert call(auth.app_login_user, 'Bearer ' + create_access_token(claims), db).id == user.id
    with pytest.raises(HTTPException):
        call(auth.app_login_user, 'Bearer ' + create_refresh_token(claims), db)
    with pytest.raises(HTTPException):
        call(auth.app_login_user, 'Bearer ' + create_access_token({'sub': str(user.id)}), db)
    call(auth.app_login_confirm, item['id'], auth.AppLoginCode(code=item['code']), user)
    call(auth.app_login_confirm, item['id'], auth.AppLoginCode(code=item['code']), user)
    assert call(auth.app_login_pending, user)['items'] == []
    approved = call(auth.app_login_status, auth.AppLoginState(state=started['state']))
    session = call(auth.app_login_complete, auth.AppLoginTicket(ticket=approved['ticket']), db)
    payload = decode_token(session.access_token, audience=auth.settings.JWT_ACCESS_AUDIENCE, token_use='access')
    assert payload['sub'] == str(user.id) and payload['principal_type'] == 'human'
    assert payload['amr'] == ['otp']
    assert cache.hget(auth.app_login_key(item['id']), 'code') is None
    with pytest.raises(HTTPException) as denied:
        call(auth.app_login_complete, auth.AppLoginTicket(ticket=approved['ticket']), db)
    assert denied.value.status_code == 401


def test_cancel_expiry_disabled_and_unknown_account(environment):
    cache, db, user, _, _ = environment
    started, item = start(environment)
    call(auth.app_login_cancel, item['id'], user)
    assert call(auth.app_login_pending, user)['items'] == []
    assert call(auth.app_login_status, auth.AppLoginState(state=started['state']))['status'] == 'cancelled'
    with pytest.raises(HTTPException):
        call(auth.app_login_confirm, item['id'], auth.AppLoginCode(code=item['code']), user)
    started, item = start(environment)
    cache.delete(auth.app_login_key(item['id']))
    with pytest.raises(HTTPException) as denied:
        call(auth.app_login_status, auth.AppLoginState(state=started['state']))
    assert denied.value.status_code == 410
    token = create_access_token({'sub': str(user.id), **human_principal_claims('sms')})
    user.status = 'disabled'; db.commit()
    with pytest.raises(HTTPException) as denied:
        call(auth.app_login_user, 'Bearer ' + token, db)
    assert denied.value.status_code == 403
    unknown = call(auth.app_login_start, auth.AppLoginStart(phone='19900000002'), db)
    assert set(unknown) == {'state', 'expires_at'}
    assert call(auth.app_login_status, auth.AppLoginState(state=unknown['state']))['status'] == 'pending'
    with pytest.raises(HTTPException) as denied:
        call(auth.app_login_start, auth.AppLoginStart(phone='19900000002'), db)
    assert denied.value.status_code == 429


def test_parallel_ticket_exchange_only_one_succeeds(environment):
    cache, db, user, _, sessions = environment
    started, item = start(environment)
    call(auth.app_login_confirm, item['id'], auth.AppLoginCode(code=item['code']), user)
    ticket = call(auth.app_login_status, auth.AppLoginState(state=started['state']))['ticket']
    def exchange(_):
        with sessions() as session:
            try:
                call(auth.app_login_complete, auth.AppLoginTicket(ticket=ticket), session)
                return 200
            except HTTPException as error:
                return error.status_code
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(exchange, range(4)))
    assert outcomes.count(200) == 1 and outcomes.count(401) == 3


def test_app_approval_secrets_never_enter_api_log():
    value = filter_sensitive_data({'state':'secret', 'ticket':'ticket', 'code':'123456', 'verification_code':'123456', 'nested':{'code':'654321'}})
    assert all(value[key] == '***' for key in ('state','ticket','code','verification_code'))
    assert value['nested']['code'] == '***'
