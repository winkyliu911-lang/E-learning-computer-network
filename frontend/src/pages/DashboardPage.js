import React, { useState } from 'react';
import { Layout, Menu, message } from 'antd';
import { Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom';
import {
  BookOutlined,
  MessageOutlined,
  HistoryOutlined,
  LogoutOutlined,
  ThunderboltOutlined,
  SolutionOutlined,
} from '@ant-design/icons';
import KnowledgeLearning from '../components/KnowledgeLearning';
import ExercisePractice from '../components/ExercisePractice';
import ExerciseHistory from '../components/ExerciseHistory';
import ChatBot from '../components/ChatBot';
import ChatHistory from '../components/ChatHistory';
import './DashboardPage.css';

const { Header, Sider, Content } = Layout;

const pathToKey = {
  '/knowledge': 'knowledge',
  '/exercises': 'exercises',
  '/exercise-history': 'exercise-history',
  '/chatbot': 'chatbot',
  '/chat-history': 'history',
};

const keyToPath = {
  'knowledge': '/knowledge',
  'exercises': '/exercises',
  'exercise-history': '/exercise-history',
  'chatbot': '/chatbot',
  'history': '/chat-history',
};

const DashboardPage = ({ user, onLogout }) => {
  const [collapsed, setCollapsed] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  const selectedKey = pathToKey[location.pathname] || 'knowledge';

  const handleLogout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user');
    message.success('已登出');
    onLogout();
    navigate('/login');
  };

  const menuItems = [
    { key: 'knowledge', icon: <BookOutlined />, label: '知识学习' },
    { key: 'exercises', icon: <ThunderboltOutlined />, label: '习题练习' },
    { key: 'exercise-history', icon: <SolutionOutlined />, label: '练习记录' },
    { key: 'chatbot', icon: <MessageOutlined />, label: 'ChatBot' },
    { key: 'history', icon: <HistoryOutlined />, label: '历史记录' },
    { key: 'logout', icon: <LogoutOutlined />, label: '登出', danger: true },
  ];

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        theme="light"
      >
        <div className="logo">
          <h2>E-Learning</h2>
        </div>
        <Menu
          theme="light"
          mode="inline"
          selectedKeys={[selectedKey]}
          items={menuItems}
          onClick={(e) => {
            if (e.key === 'logout') {
              handleLogout();
            } else {
              navigate(keyToPath[e.key]);
            }
          }}
        />
      </Sider>
      <Layout>
        <Header className="header">
          <div className="user-info">
            欢迎，{user?.username || '用户'}
          </div>
        </Header>
        <Content className="content">
          <Routes>
            <Route path="/knowledge" element={<KnowledgeLearning />} />
            <Route path="/exercises" element={<ExercisePractice />} />
            <Route path="/exercise-history" element={<ExerciseHistory />} />
            <Route path="/chatbot" element={<ChatBot />} />
            <Route path="/chat-history" element={<ChatHistory />} />
            <Route path="*" element={<Navigate to="/knowledge" replace />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  );
};

export default DashboardPage;
