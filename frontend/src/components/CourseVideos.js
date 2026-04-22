import React, { useState, useEffect } from 'react';
import { Row, Col, Card, Button, Spin, message, Empty, Tag, Modal, Input, Space } from 'antd';
import { PlayCircleOutlined, SearchOutlined, ReloadOutlined } from '@ant-design/icons';
import { videoAPI } from '../api';
import './CourseVideos.css';

const CourseVideos = () => {
  const [videos, setVideos] = useState([]);
  const [filteredVideos, setFilteredVideos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedCategory, setSelectedCategory] = useState(null);
  const [searchText, setSearchText] = useState('');
  const [selectedVideo, setSelectedVideo] = useState(null);
  const [modalVisible, setModalVisible] = useState(false);

  useEffect(() => {
    // 每次挂载时强制刷新课程数据，确保显示最新的课程
    fetchVideos();
    
    // 可选：设置定时刷新（每30秒检查一次新数据）
    const refreshInterval = setInterval(() => {
      fetchVideos();
    }, 30000);
    
    return () => clearInterval(refreshInterval);
  }, []);

  useEffect(() => {
    filterVideos();
  }, [videos, selectedCategory, searchText]);

  const fetchVideos = async () => {
    setLoading(true);
    try {
      const response = await videoAPI.getAll();
      setVideos(response.data);
    } catch (error) {
      message.error('获取视频失败');
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  const filterVideos = () => {
    let filtered = videos;

    if (selectedCategory) {
      filtered = filtered.filter((v) => v.category === selectedCategory);
    }

    if (searchText) {
      const lowerSearch = searchText.toLowerCase();
      filtered = filtered.filter((v) =>
        v.title.toLowerCase().includes(lowerSearch) ||
        v.description.toLowerCase().includes(lowerSearch)
      );
    }

    setFilteredVideos(filtered);
  };

  const categories = [...new Set(videos.map((v) => v.category))].sort();

  const handleWatch = (video) => {
    setSelectedVideo(video);
    setModalVisible(true);
  };

  // 转换 B站链接为可嵌入的 iframe 链接
  const getBilibiliEmbedUrl = (url) => {
    if (!url) return '';
    
    // 支持多种 B站链接格式
    // 格式1: https://www.bilibili.com/video/BV1JV411t7zt
    // 格式2: https://bilibili.com/video/BV1JV411t7zt
    // 格式3: BV1JV411t7zt (直接 BV ID)
    
    let bvid = '';
    
    if (url.includes('bilibili.com')) {
      const match = url.match(/BV[\w]+/);
      if (match) {
        bvid = match[0];
      }
    } else if (url.startsWith('BV')) {
      bvid = url;
    }
    
    if (bvid) {
      // 返回 B站官方的嵌入链接格式
      return `https://player.bilibili.com/player.html?bvid=${bvid}`;
    }
    
    // 如果是 YouTube 或其他嵌入链接，直接返回
    return url;
  };

  return (
    <div className="course-videos">
      <div className="videos-header">
        <h2>计算机网络课程</h2>
        <p className="subtitle">系统学习计算机网络基础知识</p>
      </div>

      <div className="videos-filter">
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
            <Input
              prefix={<SearchOutlined />}
              placeholder="搜索课程标题或描述..."
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              allowClear
              size="large"
              style={{ flex: 1 }}
            />
            <Button
              type="primary"
              icon={<ReloadOutlined />}
              onClick={() => {
                fetchVideos();
                message.success('课程已刷新');
              }}
              size="large"
              title="刷新课程列表"
            >
              刷新
            </Button>
          </div>

          <div className="category-filter">
            <Button
              type={selectedCategory === null ? 'primary' : 'default'}
              onClick={() => setSelectedCategory(null)}
              className="filter-button"
            >
              全部课程 ({videos.length})
            </Button>
            {categories.map((category) => (
              <Button
                key={category}
                type={selectedCategory === category ? 'primary' : 'default'}
                onClick={() => setSelectedCategory(category)}
                className="filter-button"
              >
                {category} ({videos.filter((v) => v.category === category).length})
              </Button>
            ))}
          </div>
        </Space>
      </div>

      <Spin spinning={loading} tip="加载中...">
        {filteredVideos.length === 0 ? (
          <Empty
            description={searchText || selectedCategory ? '未找到匹配的课程' : '暂无视频课程'}
            style={{ marginTop: '50px' }}
          />
        ) : (
          <>
            <div className="results-info">
              找到 <span className="count">{filteredVideos.length}</span> 个课程
            </div>
            <Row gutter={[16, 16]}>
              {filteredVideos.map((video) => (
                <Col key={video.id} xs={24} sm={12} lg={8}>
                  <Card
                    hoverable
                    className="video-card"
                    cover={
                      <div className="video-cover">
                        <div className="play-button">
                          <PlayCircleOutlined className="play-icon" />
                        </div>
                        <div className="video-emoji-cover">
                          📹
                        </div>
                      </div>
                    }
                  >
                    <Card.Meta
                      title={
                        <span className="video-title" title={video.title}>
                          {video.title}
                        </span>
                      }
                      description={
                        <div className="video-meta">
                          <p className="video-description">{video.description}</p>
                          <div className="video-tags">
                            <Tag color="cyan">{video.category}</Tag>
                          </div>
                        </div>
                      }
                    />
                    <Button
                      type="primary"
                      block
                      size="large"
                      icon={<PlayCircleOutlined />}
                      onClick={() => handleWatch(video)}
                      className="watch-button"
                    >
                      开始学习
                    </Button>
                  </Card>
                </Col>
              ))}
            </Row>
          </>
        )}
      </Spin>

      <Modal
        title={selectedVideo?.title}
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        footer={null}
        width={900}
        centered
        className="video-modal"
      >
        {selectedVideo && (
          <div className="video-player">
            <iframe
              width="100%"
              height="500"
              src={getBilibiliEmbedUrl(selectedVideo.video_url)}
              frameBorder="0"
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
              allowFullScreen
              title={selectedVideo.title}
              style={{ borderRadius: '8px' }}
            />
            <div className="video-info">
              <h3>{selectedVideo.title}</h3>
              <p>{selectedVideo.description}</p>
              <div className="info-row">
                <span>
                  <strong>分类:</strong> {selectedVideo.category}
                </span>
              </div>
              <Button
                type="primary"
                size="large"
                block
                onClick={() => window.open(selectedVideo.video_url, '_blank')}
              >
                在 B站 中打开
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default CourseVideos;
