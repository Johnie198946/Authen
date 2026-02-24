"""
CSRF防护属性测试

使用Hypothesis进行基于属性的测试，验证CSRF保护机制。

属性 29：CSRF攻击防护
对于任意状态改变的API请求（POST、PUT、DELETE），如果请求缺少有效的CSRF Token，
系统应该拒绝该请求。

验证需求：11.2
"""
from hypothesis import given, strategies as st, settings, HealthCheck
from fastapi import FastAPI
from fastapi.testclient import TestClient
from shared.middleware.csrf_protection import CSRFProtectionMiddleware
from shared.utils.csrf import generate_csrf_token
import json


# ==================== 测试策略 ====================

# HTTP方法策略（状态改变的方法）
http_methods = st.sampled_from(['POST', 'PUT', 'DELETE', 'PATCH'])

# 路径策略
api_paths = st.sampled_from([
    '/api/v1/users',
    '/api/v1/roles',
    '/api/v1/permissions',
    '/api/v1/organizations',
    '/api/v1/subscriptions',
    '/api/v1/admin/cloud-services',
    '/api/v1/admin/templates',
])

# 请求体策略
request_bodies = st.one_of(
    st.none(),
    st.dictionaries(
        keys=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=('Lu', 'Ll'))),
        values=st.one_of(
            st.text(max_size=50),
            st.integers(),
            st.booleans()
        ),
        min_size=0,
        max_size=5
    )
)

# Token策略
csrf_tokens = st.one_of(
    st.none(),  # 没有Token
    st.just(''),  # 空Token
    st.text(min_size=1, max_size=10, alphabet='0123456789abcdef'),  # 短Token
    st.text(min_size=1, max_size=100, alphabet=st.characters(min_codepoint=32, max_codepoint=126)),  # ASCII可打印字符
)


# ==================== 属性测试 ====================

@given(
    method=http_methods,
    path=api_paths,
    body=request_bodies
)
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture]
)
def test_csrf_property_reject_requests_without_valid_token(method, path, body):
    """
    **属性 29：CSRF攻击防护**
    
    **验证需求：11.2**
    
    属性：对于任意状态改变的API请求（POST、PUT、DELETE、PATCH），
    如果请求缺少有效的CSRF Token，系统应该拒绝该请求。
    
    测试策略：
    - 生成随机的HTTP方法（POST、PUT、DELETE、PATCH）
    - 生成随机的API路径
    - 生成随机的请求体
    - 不提供CSRF Token或提供无效Token
    - 验证请求被拒绝（403错误）
    """
    # 创建测试应用
    app = FastAPI()
    app.add_middleware(CSRFProtectionMiddleware)
    
    # 添加测试端点
    @app.post(path)
    @app.put(path)
    @app.delete(path)
    @app.patch(path)
    async def test_endpoint():
        return {"message": "success"}
    
    client = TestClient(app, raise_server_exceptions=False)
    
    # 准备请求参数
    kwargs = {}
    # DELETE请求不支持json参数
    if body is not None and method != 'DELETE':
        kwargs['json'] = body
    
    # 发送请求（不带Token）
    if method == 'POST':
        response = client.post(path, **kwargs)
    elif method == 'PUT':
        response = client.put(path, **kwargs)
    elif method == 'DELETE':
        response = client.delete(path)
    elif method == 'PATCH':
        response = client.patch(path, **kwargs)
    
    # 验证：请求应该被拒绝
    assert response.status_code == 403, \
        f"请求应该被拒绝，但返回了 {response.status_code}，响应内容：{response.text}"


@given(
    method=http_methods,
    path=api_paths,
    body=request_bodies,
    invalid_token=csrf_tokens
)
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture]
)
def test_csrf_property_reject_requests_with_invalid_token(method, path, body, invalid_token):
    """
    **属性 29：CSRF攻击防护 - 无效Token**
    
    **验证需求：11.2**
    
    属性：对于任意状态改变的API请求，如果提供了无效的CSRF Token，
    系统应该拒绝该请求。
    
    测试策略：
    - 生成随机的HTTP方法
    - 生成随机的API路径
    - 生成随机的请求体
    - 提供无效的CSRF Token
    - 验证请求被拒绝（403错误）
    """
    # 跳过None和空字符串（这些在另一个测试中覆盖）
    if invalid_token is None or invalid_token == '':
        return
    
    # 创建测试应用
    app = FastAPI()
    app.add_middleware(CSRFProtectionMiddleware)
    
    # 添加测试端点
    @app.post(path)
    @app.put(path)
    @app.delete(path)
    @app.patch(path)
    async def test_endpoint():
        return {"message": "success"}
    
    client = TestClient(app, raise_server_exceptions=False)
    
    # 准备请求参数
    kwargs = {'headers': {'X-CSRF-Token': invalid_token}}
    # DELETE请求不支持json参数
    if body is not None and method != 'DELETE':
        kwargs['json'] = body
    
    # 发送请求（带无效Token）
    if method == 'POST':
        response = client.post(path, **kwargs)
    elif method == 'PUT':
        response = client.put(path, **kwargs)
    elif method == 'DELETE':
        response = client.delete(path, headers=kwargs['headers'])
    elif method == 'PATCH':
        response = client.patch(path, **kwargs)
    
    # 验证：请求应该被拒绝
    assert response.status_code == 403, \
        f"带无效Token的请求应该被拒绝，但返回了 {response.status_code}"


@given(
    method=http_methods,
    path=api_paths,
    body=request_bodies
)
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture]
)
def test_csrf_property_accept_requests_with_valid_token(method, path, body):
    """
    **属性 29：CSRF攻击防护 - 有效Token**
    
    **验证需求：11.2**
    
    属性：对于任意状态改变的API请求，如果提供了有效的CSRF Token，
    系统应该接受该请求。
    
    测试策略：
    - 生成随机的HTTP方法
    - 生成随机的API路径
    - 生成随机的请求体
    - 提供有效的CSRF Token
    - 验证请求被接受（200错误）
    """
    # 创建测试应用
    app = FastAPI()
    app.add_middleware(CSRFProtectionMiddleware)
    
    # 添加测试端点
    @app.post(path)
    @app.put(path)
    @app.delete(path)
    @app.patch(path)
    async def test_endpoint():
        return {"message": "success"}
    
    client = TestClient(app)
    
    # 生成有效Token
    valid_token = generate_csrf_token()
    
    # 准备请求参数
    kwargs = {'headers': {'X-CSRF-Token': valid_token}}
    # DELETE请求不支持json参数
    if body is not None and method != 'DELETE':
        kwargs['json'] = body
    
    # 发送请求（带有效Token）
    if method == 'POST':
        response = client.post(path, **kwargs)
    elif method == 'PUT':
        response = client.put(path, **kwargs)
    elif method == 'DELETE':
        response = client.delete(path, headers=kwargs['headers'])
    elif method == 'PATCH':
        response = client.patch(path, **kwargs)
    
    # 验证：请求应该被接受
    assert response.status_code == 200, \
        f"带有效Token的请求应该被接受，但返回了 {response.status_code}"
    assert response.json() == {"message": "success"}


@given(
    path=api_paths,
    body=request_bodies
)
@settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture]
)
def test_csrf_property_get_requests_dont_need_token(path, body):
    """
    **属性 29：CSRF攻击防护 - GET请求豁免**
    
    **验证需求：11.2**
    
    属性：对于GET请求，不需要CSRF Token，应该正常处理。
    
    测试策略：
    - 生成随机的API路径
    - 发送GET请求（不带Token）
    - 验证请求被接受
    """
    # 创建测试应用
    app = FastAPI()
    app.add_middleware(CSRFProtectionMiddleware)
    
    # 添加测试端点
    @app.get(path)
    async def test_endpoint():
        return {"message": "success"}
    
    client = TestClient(app)
    
    # 发送GET请求（不带Token）
    response = client.get(path)
    
    # 验证：GET请求应该被接受
    assert response.status_code == 200, \
        f"GET请求不需要Token，但返回了 {response.status_code}"
    assert response.json() == {"message": "success"}


@given(
    method=http_methods,
    body=request_bodies
)
@settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture]
)
def test_csrf_property_exempt_paths_dont_need_token(method, body):
    """
    **属性 29：CSRF攻击防护 - 豁免路径**
    
    **验证需求：11.2**
    
    属性：对于豁免路径（如登录、注册），不需要CSRF Token。
    
    测试策略：
    - 生成随机的HTTP方法
    - 使用豁免路径（登录、注册等）
    - 发送请求（不带Token）
    - 验证请求被接受
    """
    # 豁免路径
    exempt_paths = [
        '/api/v1/auth/login',
        '/api/v1/auth/register/email',
        '/api/v1/auth/register/phone',
        '/health',
    ]
    
    for path in exempt_paths:
        # 创建测试应用
        app = FastAPI()
        app.add_middleware(CSRFProtectionMiddleware)
        
        # 添加测试端点
        @app.post(path)
        @app.put(path)
        @app.delete(path)
        @app.patch(path)
        async def test_endpoint():
            return {"message": "success"}
        
        client = TestClient(app)
        
        # 准备请求参数
        kwargs = {}
        # DELETE请求不支持json参数
        if body is not None and method != 'DELETE':
            kwargs['json'] = body
        
        # 发送请求（不带Token）
        if method == 'POST':
            response = client.post(path, **kwargs)
        elif method == 'PUT':
            response = client.put(path, **kwargs)
        elif method == 'DELETE':
            response = client.delete(path)
        elif method == 'PATCH':
            response = client.patch(path, **kwargs)
        
        # 验证：豁免路径的请求应该被接受
        assert response.status_code == 200, \
            f"豁免路径 {path} 不需要Token，但返回了 {response.status_code}"


@given(
    method=http_methods,
    path=api_paths,
    body=request_bodies,
    token_location=st.sampled_from(['header', 'query', 'body'])
)
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture]
)
def test_csrf_property_token_in_different_locations(method, path, body, token_location):
    """
    **属性 29：CSRF攻击防护 - Token位置**
    
    **验证需求：11.2**
    
    属性：CSRF Token可以在不同位置传递（请求头、查询参数、请求体），
    系统都应该正确识别和验证。
    
    测试策略：
    - 生成随机的HTTP方法
    - 生成随机的API路径
    - 在不同位置传递有效Token
    - 验证请求被接受
    """
    # 创建测试应用
    app = FastAPI()
    app.add_middleware(CSRFProtectionMiddleware)
    
    # 添加测试端点
    @app.post(path)
    @app.put(path)
    @app.delete(path)
    @app.patch(path)
    async def test_endpoint():
        return {"message": "success"}
    
    client = TestClient(app)
    
    # 生成有效Token
    valid_token = generate_csrf_token()
    
    # 准备请求参数
    kwargs = {}
    
    if token_location == 'header':
        # Token在请求头
        kwargs['headers'] = {'X-CSRF-Token': valid_token}
        # DELETE请求不支持json参数
        if body is not None and method != 'DELETE':
            kwargs['json'] = body
    
    elif token_location == 'query':
        # Token在查询参数
        path_with_token = f"{path}?csrf_token={valid_token}"
        # DELETE请求不支持json参数
        if body is not None and method != 'DELETE':
            kwargs['json'] = body
        
        # 发送请求
        if method == 'POST':
            response = client.post(path_with_token, **kwargs)
        elif method == 'PUT':
            response = client.put(path_with_token, **kwargs)
        elif method == 'DELETE':
            response = client.delete(path_with_token)
        elif method == 'PATCH':
            response = client.patch(path_with_token, **kwargs)
        
        # 验证
        assert response.status_code == 200, \
            f"Token在查询参数中应该被接受，但返回了 {response.status_code}"
        return
    
    elif token_location == 'body':
        # Token在请求体
        if body is None:
            body = {}
        body['csrf_token'] = valid_token
        # DELETE请求不支持json参数，跳过body location测试
        if method == 'DELETE':
            return
        kwargs['json'] = body
    
    # 发送请求
    if method == 'POST':
        response = client.post(path, **kwargs)
    elif method == 'PUT':
        response = client.put(path, **kwargs)
    elif method == 'DELETE':
        response = client.delete(path, headers=kwargs.get('headers', {}))
    elif method == 'PATCH':
        response = client.patch(path, **kwargs)
    
    # 验证：请求应该被接受
    assert response.status_code == 200, \
        f"Token在{token_location}中应该被接受，但返回了 {response.status_code}"


# ==================== 边界测试 ====================

@given(
    token_length=st.integers(min_value=0, max_value=200)
)
@settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture]
)
def test_csrf_property_token_length_validation(token_length):
    """
    **属性 29：CSRF攻击防护 - Token长度验证**
    
    **验证需求：11.2**
    
    属性：只有正确长度的Token才被认为是有效的。
    
    测试策略：
    - 生成不同长度的Token
    - 验证只有64字符的hex Token被接受
    """
    # 创建测试应用
    app = FastAPI()
    app.add_middleware(CSRFProtectionMiddleware)
    
    @app.post("/test")
    async def test_endpoint():
        return {"message": "success"}
    
    client = TestClient(app, raise_server_exceptions=False)
    
    # 生成指定长度的Token
    if token_length == 64:
        # 正确长度的有效Token
        token = generate_csrf_token()
        response = client.post("/test", headers={'X-CSRF-Token': token})
        assert response.status_code == 200, \
            f"64字符的有效Token应该被接受"
    else:
        # 错误长度的Token
        token = 'a' * token_length
        response = client.post("/test", headers={'X-CSRF-Token': token})
        assert response.status_code == 403, \
            f"长度为{token_length}的Token应该被拒绝"


# ==================== 总结 ====================

def test_csrf_properties_summary():
    """
    CSRF防护属性测试总结
    
    本测试文件包含以下属性测试：
    
    1. test_csrf_property_reject_requests_without_valid_token
       - 验证缺少Token的请求被拒绝
       - 100个测试用例
    
    2. test_csrf_property_reject_requests_with_invalid_token
       - 验证无效Token的请求被拒绝
       - 100个测试用例
    
    3. test_csrf_property_accept_requests_with_valid_token
       - 验证有效Token的请求被接受
       - 100个测试用例
    
    4. test_csrf_property_get_requests_dont_need_token
       - 验证GET请求不需要Token
       - 50个测试用例
    
    5. test_csrf_property_exempt_paths_dont_need_token
       - 验证豁免路径不需要Token
       - 50个测试用例
    
    6. test_csrf_property_token_in_different_locations
       - 验证Token可以在不同位置传递
       - 100个测试用例
    
    7. test_csrf_property_token_length_validation
       - 验证Token长度验证
       - 50个测试用例
    
    总计：550个测试用例
    
    验证需求：11.2 - 实现CSRF保护机制
    验证属性：属性 29 - CSRF攻击防护
    """
    pass
