import React, { useEffect, useRef, useState } from 'react';
import { Input, Button, Spin, message, Upload, Space } from 'antd';
import { SendOutlined, PlusOutlined, CloseOutlined } from '@ant-design/icons';
import { chatAPI } from '../api';
import './ChatBot.css';

const ChatBot = () => {
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [uploadedItems, setUploadedItems] = useState([]);
  const previewUrlsRef = useRef([]);
  const sessionIdRef = useRef('');
  const [showWelcome, setShowWelcome] = useState(true);

  const createSessionId = () => {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) {
      return crypto.randomUUID();
    }
    return `session_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
  };

  if (!sessionIdRef.current) {
    sessionIdRef.current = createSessionId();
  }

  // 初始化时显示欢迎消息
  useEffect(() => {
    if (showWelcome && messages.length === 0) {
      const welcomeMessage = {
        id: Date.now(),
        type: 'bot',
        content: '我是计算机网络知识学习小助手，欢迎向我提问！',
        timestamp: new Date().toLocaleTimeString(),
      };
      setMessages([welcomeMessage]);
      setShowWelcome(false);
    }
  }, [showWelcome, messages.length]);

  useEffect(() => {
    previewUrlsRef.current = uploadedItems
      .map((item) => item.previewUrl)
      .filter(Boolean);
  }, [uploadedItems]);

  useEffect(() => {
    return () => {
      previewUrlsRef.current.forEach((url) => URL.revokeObjectURL(url));
    };
  }, []);

  // 格式化回复：按点分行显示
  const formatBotReply = (text) => {
    if (!text) return text;

    // 方法：按照中文句号、换行符等分割
    let result = text
      .split('\n')  // 先按换行分割
      .map(line => line.trim())
      .filter(line => line.length > 0);

    // 如果只有一行，再尝试按中文句号分割
    if (result.length === 1) {
      result = text
        .split(/(?<=[。！？）])/g)  // 按句号、感叹号、问号、括号后分割
        .map(line => line.trim())
        .filter(line => line.length > 0);
    }

    // 如果分割结果超过1行，返回数组；否则返回原文本
    return result.length > 1 ? result : text;
  };

  const serializeHistoryMessages = (messageList) => {
    if (!Array.isArray(messageList)) return [];

    return messageList
      .map((item) => {
        if (!item || !item.type) return null;

        const role = item.type === 'user' ? 'user' : item.type === 'bot' ? 'assistant' : null;
        if (!role) return null;

        let contentText = '';
        if (Array.isArray(item.content)) {
          contentText = item.content.join('\n');
        } else if (typeof item.content === 'string') {
          contentText = item.content;
        } else {
          contentText = JSON.stringify(item.content || '');
        }

        const normalized = String(contentText || '').trim();
        if (!normalized || normalized.startsWith('❌')) return null;

        return {
          role,
          content: normalized,
        };
      })
      .filter(Boolean);
  };

  const handleSendMessage = async () => {
    if (!inputValue.trim()) {
      message.warning('请输入问题文本');
      return;
    }

    const userMessage = {
      id: Date.now(),
      type: 'user',
      content: inputValue,
      files: uploadedItems.map((item) => item.file.name),
      imageUrls: uploadedItems.map((item) => item.previewUrl).filter(Boolean),
      timestamp: new Date().toLocaleTimeString(),
    };

    const historyMessages = serializeHistoryMessages(messages);

    setMessages([...messages, userMessage]);
    setInputValue('');
    setLoading(true);

    try {
      const response = await chatAPI.create(
        inputValue,
        uploadedItems.map((item) => item.file),
        historyMessages,
        sessionIdRef.current
      );
      const botMessage = {
        id: Date.now() + 1,
        type: 'bot',
        content: formatBotReply(response.data.answer),
        timestamp: new Date().toLocaleTimeString(),
      };
      setMessages((prev) => [...prev, botMessage]);
      uploadedItems.forEach((item) => {
        if (item.previewUrl) {
          URL.revokeObjectURL(item.previewUrl);
        }
      });
      setUploadedItems([]);
    } catch (error) {
      const errorReason = error?.response?.data?.error || error?.message || '获取回答失败';
      const botErrorMessage = {
        id: Date.now() + 1,
        type: 'bot',
        content: `❌ ${errorReason}`,
        timestamp: new Date().toLocaleTimeString(),
      };
      setMessages((prev) => [...prev, botErrorMessage]);
    } finally {
      setLoading(false);
    }
  };

  // 处理按键：Ctrl+Enter 发送，Enter 换行
  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const handleFileUpload = (file) => {
    const fileName = (file.name || '').toLowerCase();
    const ext = fileName.includes('.') ? fileName.slice(fileName.lastIndexOf('.')) : '';
    const imageExtSet = new Set(['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']);

    const isImage = file.type.startsWith('image/') || imageExtSet.has(ext);
    const isPdf = ext === '.pdf';
    const isDocx = ext === '.docx';

    if (!isImage && !isPdf && !isDocx) {
      message.error('仅支持上传图片、PDF、DOCX 文件');
      return Upload.LIST_IGNORE;
    }

    if (uploadedItems.length >= 6) {
      message.warning('最多上传 6 个文件');
      return Upload.LIST_IGNORE;
    }

    const item = {
      file,
      kind: isImage ? 'image' : isPdf ? 'pdf' : 'docx',
      previewUrl: isImage ? URL.createObjectURL(file) : null,
    };

    setUploadedItems((prev) => [...prev, item]);
    message.success(`文件已选择：${file.name}`);
    return false; // 阻止自动上传
  };

  const handleRemoveFile = (index) => {
    setUploadedItems((prev) => {
      const target = prev[index];
      if (target?.previewUrl) {
        URL.revokeObjectURL(target.previewUrl);
      }
      return prev.filter((_, i) => i !== index);
    });
  };

  // 知识库由服务端内置，前端不允许上传或初始化

  return (
    <div className="chatbot">
      <h2>ChatBot</h2>

      <div className="chat-messages">
        {messages.map((message) => (
          <div
            key={message.id}
            className={`message ${message.type} ${message.type === 'bot' && message.content.includes('计算机网络知识学习小助手') ? 'welcome-message' : ''}`}
          >
            <div className="message-content">
              {message.type === 'bot' && Array.isArray(message.content) ? (
                // Bot 回复为数组：按列表显示
                <ul className="reply-list">
                  {message.content.map((item, idx) => (
                    <li key={idx}>{item}</li>
                  ))}
                </ul>
              ) : (
                // 普通回复：按段落显示
                <p>{typeof message.content === 'string' ? message.content : JSON.stringify(message.content)}</p>
              )}
              {message.files?.length > 0 && (
                <div className="file-info">📎 {message.files.join('，')}</div>
              )}
              {message.imageUrls?.length > 0 && (
                <div className="message-image-grid">
                  {message.imageUrls.map((url, idx) => (
                    <img key={idx} className="message-image" src={url} alt={`上传图片${idx + 1}`} />
                  ))}
                </div>
              )}
              {message.type !== 'bot' || !message.content.includes('计算机网络知识学习小助手') ? (
                <span className="timestamp">{message.timestamp}</span>
              ) : null}
            </div>
          </div>
        ))}
        {loading && (
          <div className="message bot">
            <div className="message-content">
              <Spin size="small" />
            </div>
          </div>
        )}
      </div>

      <div className="chat-input-area">
        {uploadedItems.length > 0 && (
          <div className="uploaded-file-list">
            {uploadedItems.map((item, index) => (
              <div key={`${item.file.name}_${index}`} className="uploaded-file-chip">
                <span className="uploaded-file-name">📎 {item.file.name}</span>
                <Button
                  className="file-remove-btn"
                  size="small"
                  type="text"
                  icon={<CloseOutlined />}
                  onClick={() => handleRemoveFile(index)}
                />
              </div>
            ))}
          </div>
        )}

        {uploadedItems.some((item) => Boolean(item.previewUrl)) && (
          <div className="uploaded-preview-grid">
            {uploadedItems.map((item, index) => (
              item.previewUrl ? <div key={`${item.file.name}_${index}`} className="uploaded-preview-item">
                <img className="uploaded-preview" src={item.previewUrl} alt={`图片预览${index + 1}`} />
                <Button
                  className="preview-remove-btn"
                  size="small"
                  type="text"
                  icon={<CloseOutlined />}
                  onClick={() => handleRemoveFile(index)}
                />
              </div> : null
            ))}
          </div>
        )}
        <Space.Compact style={{ width: '100%' }}>
          <Upload
            multiple
            maxCount={6}
            showUploadList={false}
            accept="image/*,.pdf,.docx"
            beforeUpload={handleFileUpload}
            style={{ flex: 0 }}
          >
            <Button icon={<PlusOutlined />}>上传文件</Button>
          </Upload>
          {/* 知识库为内置，前端不提供上传/初始化功能 */}
          <Input.TextArea
            placeholder="输入问题（可上传图片/PDF/DOCX）...（Ctrl+Enter 发送）"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={loading}
            rows={4}
            style={{
              resize: 'vertical',
              minHeight: '120px',
              fontSize: '14px'
            }}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={handleSendMessage}
            loading={loading}
            style={{ height: '120px' }}
          >
            发送
          </Button>
        </Space.Compact>
      </div>
    </div>
  );
};

export default ChatBot;
