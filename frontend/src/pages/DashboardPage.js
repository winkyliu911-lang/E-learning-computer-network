import React, { useState, useEffect } from 'react';
import { Layout, Menu, message } from 'antd';
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

const DashboardPage = ({ user, onLogout }) => {
  const [selectedMenu, setSelectedMenu] = useState('knowledge');
  const [collapsed, setCollapsed] = useState(false);

  const handleLogout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user');
    message.success('已登出');
    onLogout();
  };

  const menuItems = [
    {
      key: 'knowledge',
      icon: <BookOutlined />,
      label: '知识学习',
    },
    {
      key: 'exercises',
      icon: <ThunderboltOutlined />,
      label: '习题练习',
    },
    {
      key: 'exercise-history',
      icon: <SolutionOutlined />,
      label: '练习记录',
    },
    {
      key: 'chatbot',
      icon: <MessageOutlined />,
      label: 'ChatBot',
    },
    {
      key: 'history',
      icon: <HistoryOutlined />,
      label: '历史记录',
    },
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '登出',
      danger: true,
    },
  ];

  const renderContent = () => {
    switch (selectedMenu) {
      case 'knowledge':
        return <KnowledgeLearning />;
      case 'exercises':
        return <ExercisePractice />;
      case 'exercise-history':
        return <ExerciseHistory />;
      case 'chatbot':
        return <ChatBot />;
      case 'history':
        return <ChatHistory />;
      default:
        return <KnowledgeLearning />;
    }
  };

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
          selectedKeys={[selectedMenu]}
          items={menuItems}
          onClick={(e) => {
            if (e.key === 'logout') {
              handleLogout();
            } else {
              setSelectedMenu(e.key);
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
          {renderContent()}
        </Content>
      </Layout>
    </Layout>
  );
};

export default DashboardPage;
