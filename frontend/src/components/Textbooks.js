import React, { useState, useEffect } from 'react';
import { Row, Col, Card, Button, Spin, message, Empty, Tag, Drawer } from 'antd';
import { BookOutlined } from '@ant-design/icons';
import { textbookAPI } from '../api';
import './Textbooks.css';

const Textbooks = () => {
  const [textbooks, setTextbooks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedCategory, setSelectedCategory] = useState(null);
  const [selectedTextbook, setSelectedTextbook] = useState(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(() => {
    fetchTextbooks();
  }, []);

  const fetchTextbooks = async () => {
    setLoading(true);
    try {
      const response = await textbookAPI.getAll(selectedCategory);
      setTextbooks(response.data);
    } catch (error) {
      message.error('获取课本失败');
    } finally {
      setLoading(false);
    }
  };

  const categories = [...new Set(textbooks.map((t) => t.category))];

  const handleRead = async (textbook) => {
    try {
      const response = await textbookAPI.getById(textbook.id);
      setSelectedTextbook(response.data);
      setDrawerOpen(true);
    } catch (error) {
      message.error('获取课本内容失败');
    }
  };

  return (
    <div className="textbooks">
      <h2>课本学习</h2>

      <div className="category-filter">
        <Button
          type={selectedCategory === null ? 'primary' : 'default'}
          onClick={() => {
            setSelectedCategory(null);
            fetchTextbooks();
          }}
        >
          全部
        </Button>
        {categories.map((category) => (
          <Button
            key={category}
            type={selectedCategory === category ? 'primary' : 'default'}
            onClick={() => {
              setSelectedCategory(category);
            }}
          >
            {category}
          </Button>
        ))}
      </div>

      <Spin spinning={loading}>
        {textbooks.length === 0 ? (
          <Empty description="暂无课本" />
        ) : (
          <Row gutter={[16, 16]}>
            {textbooks.map((textbook) => (
              <Col key={textbook.id} xs={24} sm={12} lg={8}>
                <Card
                  hoverable
                  className="textbook-card"
                  cover={
                    <div className="textbook-cover">
                      <BookOutlined className="book-icon" />
                    </div>
                  }
                >
                  <Card.Meta
                    title={textbook.title}
                    description={
                      <>
                        <p>{textbook.description}</p>
                        <Tag color="green">{textbook.category}</Tag>
                      </>
                    }
                  />
                  <Button
                    type="primary"
                    block
                    onClick={() => handleRead(textbook)}
                  >
                    阅读课本
                  </Button>
                </Card>
              </Col>
            ))}
          </Row>
        )}
      </Spin>

      <Drawer
        title={selectedTextbook?.title}
        placement="right"
        onClose={() => setDrawerOpen(false)}
        open={drawerOpen}
        width={600}
      >
        {selectedTextbook && (
          <div className="textbook-content">
            <p>
              <strong>分类：</strong> {selectedTextbook.category}
            </p>
            <p>
              <strong>描述：</strong> {selectedTextbook.description}
            </p>
            <div className="content">
              <h4>课本内容：</h4>
              <p>{selectedTextbook.content}</p>
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
};

export default Textbooks;
