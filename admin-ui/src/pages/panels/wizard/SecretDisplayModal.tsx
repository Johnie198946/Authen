import { Modal, Button, Typography } from 'antd';

const { Paragraph } = Typography;

interface SecretDisplayModalProps {
  open: boolean;
  appId: string;
  appSecret: string;
  onClose: () => void;
}

export default function SecretDisplayModal({ open, appId, appSecret, onClose }: SecretDisplayModalProps) {
  return (
    <Modal
      title="应用密钥"
      open={open}
      onCancel={onClose}
      footer={[
        <Button key="ok" type="primary" onClick={onClose}>
          我已保存
        </Button>,
      ]}
    >
      <div style={{ marginBottom: 16, color: '#ff4d4f', fontWeight: 'bold' }}>
        ⚠️ 请妥善保存以下密钥，关闭后将无法再次查看！
      </div>
      <div style={{ marginBottom: 12 }}>
        <div style={{ color: '#666', marginBottom: 4 }}>App ID:</div>
        <Paragraph copyable style={{ marginBottom: 0 }}>
          {appId}
        </Paragraph>
      </div>
      <div>
        <div style={{ color: '#666', marginBottom: 4 }}>App Secret:</div>
        <Paragraph copyable style={{ marginBottom: 0, wordBreak: 'break-all' }}>
          {appSecret}
        </Paragraph>
      </div>
    </Modal>
  );
}
