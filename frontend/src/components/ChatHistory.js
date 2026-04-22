import React, { useState, useEffect } from 'react';
import { Table, Button, Spin, message, Empty, Drawer, Popconfirm, Space } from 'antd';
import { EyeOutlined, DeleteOutlined } from '@ant-design/icons';
import { chatAPI } from '../api';
import './ChatHistory.css';

const ChatHistory = () => {
  const [sessionHistory, setSessionHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedSession, setSelectedSession] = useState(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(() => {
    fetchChatHistory();
  }, []);

  const fetchChatHistory = async () => {
    setLoading(true);
    try {
      const response = await chatAPI.getHistory();
      console.log('📜 聊天历史记录获取成功:', response.data);
      const records = Array.isArray(response.data) ? response.data : [];
      setSessionHistory(buildSessionList(records));
    } catch (error) {
      console.error('❌ 获取聊天历史失败:', error);
      if (error.response) {
        message.error(`获取历史记录失败: ${error.response.data?.error || error.response.statusText}`);
      } else if (error.request) {
        message.error('无法连接到服务器，请检查后端是否启动');
      } else {
        message.error('获取聊天历史失败: ' + error.message);
      }
      setSessionHistory([]);
    } finally {
      setLoading(false);
    }
  };

  const parseConversation = (record) => {
    if (!record) return [];

    if (record.conversation_json) {
      try {
        const parsed = JSON.parse(record.conversation_json);
        if (Array.isArray(parsed)) {
          return parsed
            .map((item) => {
              if (!item || !item.role || !item.content) return null;
              return {
                role: item.role,
                content: String(item.content),
              };
            })
            .filter(Boolean);
        }
      } catch (e) {
        console.warn('解析 conversation_json 失败:', e);
      }
    }

    const fallback = [];
    if (record.question) {
      fallback.push({ role: 'user', content: String(record.question) });
    }
    if (record.answer) {
      fallback.push({ role: 'assistant', content: String(record.answer) });
    }
    return fallback;
  };

  const buildSessionList = (records) => {
    const groups = {};

    records.forEach((record) => {
      const sid = record.session_id || `legacy_${record.id}`;
      if (!groups[sid]) {
        groups[sid] = {
          session_id: sid,
          chat_ids: [],
          turns: [],
          created_at: record.created_at,
          latest_question: '',
        };
      }

      groups[sid].chat_ids.push(record.id);
      const turns = parseConversation(record);
      if (turns.length > 0) {
        groups[sid].turns = turns;
      }

      const latestQuestion = turns.filter((t) => t.role === 'user').slice(-1)[0]?.content || record.question || '';
      groups[sid].latest_question = latestQuestion;

      if (!groups[sid].created_at || new Date(record.created_at) > new Date(groups[sid].created_at)) {
        groups[sid].created_at = record.created_at;
      }
    });

    return Object.values(groups)
      .map((session) => ({
        ...session,
        turn_count: session.turns.filter((t) => t.role === 'user').length,
      }))
      .sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
  };

  const handleViewSession = (session) => {
    setSelectedSession(session);
    setDrawerOpen(true);
  };

  const handleDeleteSession = async (sessionId) => {
    try {
      await chatAPI.deleteSessionHistory(sessionId);
      message.success('会话已删除');
      fetchChatHistory(); // 刷新列表
    } catch (error) {
      console.error('❌ 删除失败:', error);
      message.error('删除失败');
    }
  };

  const handleDeleteAllChat = async () => {
    try {
      await chatAPI.deleteAllHistory();
      message.success('所有聊天记录已删除');
      setSessionHistory([]);
    } catch (error) {
      console.error('❌ 删除所有记录失败:', error);
      message.error('删除失败');
    }
  };

  const columns = [
    {
      title: '最近问题',
      dataIndex: 'latest_question',
      key: 'latest_question',
      width: '50%',
      render: (text) => {
        const value = text || '（暂无）';
        return value.length > 50 ? `${value.substring(0, 50)}...` : value;
      },
    },
    {
      title: '轮数',
      dataIndex: 'turn_count',
      key: 'turn_count',
      width: '10%',
    },
    {
      title: '更新时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: '15%',
      render: (date) => new Date(date).toLocaleString('zh-CN'),
    },
    {
      title: '操作',
      key: 'action',
      width: '15%',
      render: (_, record) => (
        <Space>
          <Button
            type="primary"
            size="small"
            icon={<EyeOutlined />}
            onClick={() => handleViewSession(record)}
          >
            展开
          </Button>
          <Popconfirm
            title="删除会话"
            description="确定要删除整个会话吗？"
            onConfirm={() => handleDeleteSession(record.session_id)}
            okText="删除"
            cancelText="取消"
          >
            <Button
              danger
              size="small"
              icon={<DeleteOutlined />}
            >
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div className="chat-history">
      <div className="history-header">
        <h2>会话历史</h2>
        {sessionHistory.length > 0 && (
          <Popconfirm
            title="清空所有记录"
            description="确定要删除所有聊天记录吗？此操作不可撤销。"
            onConfirm={handleDeleteAllChat}
            okText="确认"
            cancelText="取消"
          >
            <Button danger type="primary">
              清空所有记录
            </Button>
          </Popconfirm>
        )}
      </div>

      <Spin spinning={loading}>
        {sessionHistory.length === 0 ? (
          <Empty description="暂无聊天记录" />
        ) : (
          <Table
            columns={columns}
            dataSource={sessionHistory}
            rowKey="session_id"
            pagination={{
              pageSize: 10,
              showTotal: (total) => `共 ${total} 条记录`,
            }}
          />
        )}
      </Spin>

      <Drawer
        title="会话详情"
        placement="right"
        onClose={() => setDrawerOpen(false)}
        open={drawerOpen}
        width={600}
      >
        {selectedSession && (
          <div className="chat-detail">
            <div className="detail-item">
              <h4>会话ID：</h4>
              <p>{selectedSession.session_id}</p>
            </div>
            <div className="detail-item">
              <h4>轮次详情：</h4>
              <div className="session-turn-list">
                {selectedSession.turns.length === 0 ? (
                  <p>暂无会话内容</p>
                ) : (
                  selectedSession.turns.map((turn, idx) => (
                    <div key={`${turn.role}-${idx}`} className={`turn-item ${turn.role}`}>
                      <div className="turn-role">{turn.role === 'user' ? '用户' : '助手'}</div>
                      <div className="turn-content">{turn.content}</div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
};

export default ChatHistory;
