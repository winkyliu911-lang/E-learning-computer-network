import React, { useState, useEffect, useCallback } from 'react';
import {
  Row, Col, Button, message, Empty, Spin, Modal, Input, Card,
  Tag, Popconfirm, Space, Tooltip, Select,
} from 'antd';
import {
  PlayCircleOutlined, FilePdfOutlined, EditOutlined,
  SaveOutlined, DeleteOutlined, SearchOutlined,
  BookOutlined, ClockCircleOutlined, FileTextOutlined,
} from '@ant-design/icons';
import CourseVideos from './CourseVideos';
import { noteAPI } from '../api';
import './KnowledgeLearning.css';

const { TextArea } = Input;
const { Option } = Select;

const KnowledgeLearning = () => {
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('videos');

  // PDF viewer state
  const [pdfUrl, setPdfUrl] = useState(null);
  const [showPdfModal, setShowPdfModal] = useState(false);
  const [currentBookTitle, setCurrentBookTitle] = useState('');

  // Notes state (in PDF modal)
  const [noteTitle, setNoteTitle] = useState('');
  const [noteContent, setNoteContent] = useState('');
  const [bookNotes, setBookNotes] = useState([]);
  const [noteSaving, setNoteSaving] = useState(false);

  // Notes tab state
  const [allNotes, setAllNotes] = useState([]);
  const [notesLoading, setNotesLoading] = useState(false);
  const [searchKeyword, setSearchKeyword] = useState('');
  const [filterBook, setFilterBook] = useState('');
  const [editingNote, setEditingNote] = useState(null);
  const [editTitle, setEditTitle] = useState('');
  const [editContent, setEditContent] = useState('');

  const textbookLinks = [
    {
      id: 1,
      title: '计算机网络自顶向下方法 原书第8版',
      description: '计算机网络的经典教材，涵盖网络体系结构、协议和应用等内容',
      pdfFile: '计算机网络自顶向下方法原书第8版.pdf',
      icon: '📘',
    },
    {
      id: 2,
      title: '计算机网络（第8版）(谢希仁)',
      description: '计算机网络的基础知识，涵盖网络原理、协议和技术等内容',
      pdfFile: '计算机网络第8版(谢希仁).pdf',
      icon: '📘',
    },
    {
      id: 3,
      title: 'Computer Networking: A Top-Down Approach (8th Edition)',
      description: 'A comprehensive guide to computer networking.',
      pdfFile: 'computer-networking-a-top-down-approach-8th-edition.pdf',
      icon: '📘',
    },
  ];

  const fetchBookNotes = useCallback(async (bookTitle) => {
    try {
      const res = await noteAPI.getAll({ textbook_title: bookTitle });
      setBookNotes(res.data);
    } catch {
      // silent
    }
  }, []);

  const fetchAllNotes = useCallback(async () => {
    setNotesLoading(true);
    try {
      const params = {};
      if (filterBook) params.textbook_title = filterBook;
      if (searchKeyword) params.keyword = searchKeyword;
      const res = await noteAPI.getAll(params);
      setAllNotes(res.data);
    } catch {
      message.error('加载笔记失败');
    } finally {
      setNotesLoading(false);
    }
  }, [filterBook, searchKeyword]);

  useEffect(() => {
    if (activeTab === 'notes') {
      fetchAllNotes();
    }
  }, [activeTab, fetchAllNotes]);

  const handleOpenPdf = (pdfFile, bookTitle) => {
    const fileUrl = `http://localhost:8000/api/files/textbooks/${encodeURIComponent(pdfFile)}`;
    if (pdfFile.toLowerCase().endsWith('.pdf')) {
      setPdfUrl(fileUrl);
      setCurrentBookTitle(bookTitle);
      setShowPdfModal(true);
      setNoteTitle('');
      setNoteContent('');
      fetchBookNotes(bookTitle);
    } else {
      window.open(fileUrl, '_blank');
    }
  };

  const handleSaveNote = async () => {
    if (!noteTitle.trim() || !noteContent.trim()) {
      message.warning('请输入笔记标题和内容');
      return;
    }
    setNoteSaving(true);
    try {
      await noteAPI.create({
        textbook_title: currentBookTitle,
        title: noteTitle.trim(),
        content: noteContent.trim(),
      });
      message.success('笔记已保存');
      setNoteTitle('');
      setNoteContent('');
      fetchBookNotes(currentBookTitle);
    } catch {
      message.error('保存失败');
    } finally {
      setNoteSaving(false);
    }
  };

  const handleDeleteNote = async (id) => {
    try {
      await noteAPI.delete(id);
      message.success('已删除');
      fetchBookNotes(currentBookTitle);
      if (activeTab === 'notes') fetchAllNotes();
    } catch {
      message.error('删除失败');
    }
  };

  const handleUpdateNote = async () => {
    if (!editTitle.trim() || !editContent.trim()) return;
    try {
      await noteAPI.update(editingNote, { title: editTitle, content: editContent });
      message.success('已更新');
      setEditingNote(null);
      fetchAllNotes();
    } catch {
      message.error('更新失败');
    }
  };

  const formatTime = (iso) => {
    if (!iso) return '';
    const d = new Date(iso);
    return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  };

  return (
    <div className="knowledge-learning">
      <div className="learning-header">
        <h2>知识学习中心</h2>
        <div className="tab-buttons">
          <Button
            type={activeTab === 'videos' ? 'primary' : 'default'}
            onClick={() => setActiveTab('videos')}
            icon={<PlayCircleOutlined />}
            size="large"
          >
            课程视频
          </Button>
          <Button
            type={activeTab === 'textbooks' ? 'primary' : 'default'}
            onClick={() => setActiveTab('textbooks')}
            icon={<FilePdfOutlined />}
            size="large"
          >
            教科书
          </Button>
          <Button
            type={activeTab === 'notes' ? 'primary' : 'default'}
            onClick={() => setActiveTab('notes')}
            icon={<EditOutlined />}
            size="large"
          >
            我的笔记
          </Button>
        </div>
      </div>

      <Spin spinning={loading}>
        {activeTab === 'videos' && (
          <div className="learning-content">
            <div className="videos-section">
              <h3>课程视频</h3>
              <CourseVideos />
            </div>
          </div>
        )}

        {activeTab === 'textbooks' && (
          <div className="textbooks-full-section">
            <Row gutter={[16, 16]}>
              {textbookLinks.map((book) => (
                <Col xs={24} sm={12} lg={8} key={book.id}>
                  <div className="textbook-full-card">
                    <div className="textbook-icon">{book.icon}</div>
                    <h3>{book.title}</h3>
                    <p>{book.description}</p>
                    <Button
                      type="primary"
                      size="large"
                      icon={<FilePdfOutlined />}
                      block
                      onClick={() => handleOpenPdf(book.pdfFile, book.title)}
                    >
                      打开阅读
                    </Button>
                  </div>
                </Col>
              ))}
            </Row>
          </div>
        )}

        {activeTab === 'notes' && (
          <div className="notes-tab-section">
            <Card className="notes-filter-card">
              <Space wrap style={{ width: '100%', justifyContent: 'space-between' }}>
                <Space wrap>
                  <Input
                    placeholder="搜索笔记..."
                    prefix={<SearchOutlined />}
                    value={searchKeyword}
                    onChange={(e) => setSearchKeyword(e.target.value)}
                    onPressEnter={fetchAllNotes}
                    style={{ width: 220 }}
                    allowClear
                  />
                  <Select
                    placeholder="筛选教科书"
                    allowClear
                    style={{ width: 200 }}
                    value={filterBook || undefined}
                    onChange={(v) => setFilterBook(v || '')}
                  >
                    {textbookLinks.map((b) => (
                      <Option key={b.id} value={b.title}>{b.title}</Option>
                    ))}
                  </Select>
                  <Button icon={<SearchOutlined />} onClick={fetchAllNotes}>搜索</Button>
                </Space>
                <span className="notes-count">{allNotes.length} 条笔记</span>
              </Space>
            </Card>

            <Spin spinning={notesLoading}>
              {allNotes.length > 0 ? (
                <div className="notes-grid">
                  {allNotes.map((note) => (
                    <Card
                      key={note.id}
                      className="note-card"
                      size="small"
                    >
                      {editingNote === note.id ? (
                        <div className="note-edit-form">
                          <Input
                            value={editTitle}
                            onChange={(e) => setEditTitle(e.target.value)}
                            placeholder="标题"
                            style={{ marginBottom: 8 }}
                          />
                          <TextArea
                            value={editContent}
                            onChange={(e) => setEditContent(e.target.value)}
                            rows={4}
                            style={{ marginBottom: 8 }}
                          />
                          <Space>
                            <Button type="primary" size="small" onClick={handleUpdateNote}>保存</Button>
                            <Button size="small" onClick={() => setEditingNote(null)}>取消</Button>
                          </Space>
                        </div>
                      ) : (
                        <>
                          <div className="note-card-header">
                            <h4 className="note-card-title">
                              <FileTextOutlined style={{ marginRight: 6, color: '#1890ff' }} />
                              {note.title}
                            </h4>
                            <Space size={4}>
                              <Tooltip title="编辑">
                                <Button
                                  type="text"
                                  size="small"
                                  icon={<EditOutlined />}
                                  onClick={() => {
                                    setEditingNote(note.id);
                                    setEditTitle(note.title);
                                    setEditContent(note.content);
                                  }}
                                />
                              </Tooltip>
                              <Popconfirm title="删除此笔记？" onConfirm={() => handleDeleteNote(note.id)} okText="删除" cancelText="取消">
                                <Button type="text" size="small" danger icon={<DeleteOutlined />} />
                              </Popconfirm>
                            </Space>
                          </div>
                          <p className="note-card-content">{note.content}</p>
                          <div className="note-card-footer">
                            {note.textbook_title && (
                              <Tag color="blue" icon={<BookOutlined />}>{note.textbook_title.length > 15 ? note.textbook_title.slice(0, 15) + '...' : note.textbook_title}</Tag>
                            )}
                            <span className="note-card-time">
                              <ClockCircleOutlined style={{ marginRight: 4 }} />
                              {formatTime(note.created_at)}
                            </span>
                          </div>
                        </>
                      )}
                    </Card>
                  ))}
                </div>
              ) : (
                <Card className="empty-card">
                  <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description={searchKeyword || filterBook ? '没有符合条件的笔记' : '还没有笔记，阅读课本时可以添加'}
                  />
                </Card>
              )}
            </Spin>
          </div>
        )}
      </Spin>

      {/* PDF 阅读 + 笔记分屏模态框 */}
      <Modal
        title={`阅读 - ${currentBookTitle}`}
        open={showPdfModal}
        onCancel={() => setShowPdfModal(false)}
        footer={null}
        width="100%"
        className="pdf-notes-modal"
        style={{
          position: 'fixed',
          top: 0, left: 0, right: 0, bottom: 0,
          maxWidth: 'none',
          height: '100vh',
          margin: 0,
          padding: 0,
        }}
        bodyStyle={{ height: 'calc(100vh - 55px)', padding: 0 }}
      >
        <div className="pdf-notes-container">
          <div className="pdf-panel">
            {pdfUrl && (
              <iframe
                src={`${pdfUrl}#toolbar=1&zoom=page-fit`}
                style={{ width: '100%', height: '100%', border: 'none' }}
                title="PDF阅读"
              />
            )}
          </div>
          <div className="notes-panel">
            <div className="notes-panel-header">
              <EditOutlined style={{ marginRight: 6 }} />
              笔记
            </div>
            <div className="notes-panel-input">
              <Input
                placeholder="笔记标题"
                value={noteTitle}
                onChange={(e) => setNoteTitle(e.target.value)}
                style={{ marginBottom: 8 }}
              />
              <TextArea
                placeholder="在这里记录你的学习笔记..."
                value={noteContent}
                onChange={(e) => setNoteContent(e.target.value)}
                rows={4}
                style={{ marginBottom: 8 }}
              />
              <Button
                type="primary"
                icon={<SaveOutlined />}
                onClick={handleSaveNote}
                loading={noteSaving}
                block
              >
                保存笔记
              </Button>
            </div>
            <div className="notes-panel-list">
              <div className="notes-panel-list-header">
                已有笔记 ({bookNotes.length})
              </div>
              {bookNotes.length > 0 ? (
                bookNotes.map((note) => (
                  <div key={note.id} className="note-item">
                    <div className="note-item-header">
                      <span className="note-item-title">{note.title}</span>
                      <Popconfirm
                        title="删除此笔记？"
                        onConfirm={() => handleDeleteNote(note.id)}
                        okText="删除"
                        cancelText="取消"
                      >
                        <Button type="text" size="small" danger icon={<DeleteOutlined />} />
                      </Popconfirm>
                    </div>
                    <p className="note-item-content">{note.content}</p>
                    <span className="note-item-time">{formatTime(note.created_at)}</span>
                  </div>
                ))
              ) : (
                <div className="notes-empty-hint">暂无笔记，开始记录吧</div>
              )}
            </div>
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default KnowledgeLearning;
