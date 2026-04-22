import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Row, Col, Tag, Select, Button, Empty, Spin,
  Statistic, message, Popconfirm, Collapse, Space, Tooltip,
} from 'antd';
import {
  CheckCircleFilled, CloseCircleFilled,
  TrophyOutlined, AimOutlined, BookOutlined,
  DeleteOutlined, ClearOutlined, ReloadOutlined,
  FireOutlined, ClockCircleOutlined,
} from '@ant-design/icons';
import { exerciseAPI } from '../api';
import './ExerciseHistory.css';

const { Option } = Select;

const chapterMap = {
  physical_layer: '物理层',
  data_link_layer: '数据链路层',
  network_layer: '网络层',
  transport_layer: '传输层',
  application_layer: '应用层',
};

const difficultyColors = {
  easy: '#52c41a',
  medium: '#faad14',
  hard: '#ff4d4f',
};

const difficultyLabels = {
  easy: '简单',
  medium: '中等',
  hard: '困难',
};

const ExerciseHistory = () => {
  const [records, setRecords] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [filterChapter, setFilterChapter] = useState('');
  const [filterType, setFilterType] = useState('');
  const [filterCorrect, setFilterCorrect] = useState('');

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (filterChapter) params.chapter = filterChapter;
      if (filterType) params.question_type = filterType;
      if (filterCorrect !== '') params.is_correct = filterCorrect;

      const [historyRes, statsRes] = await Promise.all([
        exerciseAPI.getHistory(params),
        exerciseAPI.getStats(),
      ]);
      setRecords(historyRes.data);
      setStats(statsRes.data);
    } catch (err) {
      message.error('获取练习记录失败');
    } finally {
      setLoading(false);
    }
  }, [filterChapter, filterType, filterCorrect]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleDelete = async (id) => {
    try {
      await exerciseAPI.deleteRecord(id);
      message.success('已删除');
      fetchData();
    } catch {
      message.error('删除失败');
    }
  };

  const handleClearAll = async () => {
    try {
      await exerciseAPI.clearAll();
      message.success('已清空所有记录');
      fetchData();
    } catch {
      message.error('清空失败');
    }
  };

  const formatTime = (isoStr) => {
    if (!isoStr) return '';
    const d = new Date(isoStr);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  };

  const collapseItems = records.map((r) => ({
    key: String(r.id),
    label: (
      <div className="record-header">
        <div className="record-header-left">
          {r.is_correct ? (
            <CheckCircleFilled className="icon-correct" />
          ) : (
            <CloseCircleFilled className="icon-wrong" />
          )}
          <span className="record-question">{r.question}</span>
        </div>
        <div className="record-header-right">
          <Tag color={difficultyColors[r.difficulty] || '#999'}>
            {difficultyLabels[r.difficulty] || r.difficulty}
          </Tag>
          <Tag color="blue">{chapterMap[r.chapter] || r.chapter}</Tag>
          <Tag color={r.question_type === 'choice' ? 'purple' : 'cyan'}>
            {r.question_type === 'choice' ? '选择题' : '简答题'}
          </Tag>
          <span className="record-time">
            <ClockCircleOutlined style={{ marginRight: 4 }} />
            {formatTime(r.created_at)}
          </span>
        </div>
      </div>
    ),
    children: (
      <div className="record-detail">
        {r.question_type === 'choice' && r.options && (
          <div className="detail-section">
            <div className="detail-label">选项</div>
            <div className="options-list">
              {r.options.map((opt, i) => {
                const letter = String.fromCharCode(65 + i);
                const isUserAnswer = r.user_answer && r.user_answer.toUpperCase() === letter;
                const isCorrect = r.correct_answer && r.correct_answer.toUpperCase() === letter;
                let cls = 'option-item';
                if (isCorrect) cls += ' option-correct';
                if (isUserAnswer && !isCorrect) cls += ' option-wrong';
                return (
                  <div key={i} className={cls}>
                    <span className="option-letter">{letter}</span>
                    <span>{opt.replace(/^[A-Da-d][.、．:\s]+/, '')}</span>
                    {isCorrect && <Tag color="green" className="option-tag">正确答案</Tag>}
                    {isUserAnswer && !isCorrect && <Tag color="red" className="option-tag">你的答案</Tag>}
                    {isUserAnswer && isCorrect && <Tag color="green" className="option-tag">你的答案</Tag>}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {r.question_type === 'short_answer' && (
          <>
            <div className="detail-section">
              <div className="detail-label">你的回答</div>
              <div className="detail-content user-answer-box">{r.user_answer}</div>
            </div>
            {r.correct_answer && (
              <div className="detail-section">
                <div className="detail-label">参考答案</div>
                <div className="detail-content correct-answer-box">{r.correct_answer}</div>
              </div>
            )}
            {r.score !== null && r.score !== undefined && (
              <div className="detail-section">
                <div className="detail-label">得分</div>
                <div className="score-display">
                  <span className={`score-value ${r.score >= 60 ? 'score-pass' : 'score-fail'}`}>{r.score}</span>
                  <span className="score-total">/ 100</span>
                </div>
              </div>
            )}
          </>
        )}

        {r.feedback && (
          <div className="detail-section">
            <div className="detail-label">反馈</div>
            <div className="detail-content feedback-box">{r.feedback}</div>
          </div>
        )}

        {r.explanation && (
          <div className="detail-section">
            <div className="detail-label">解析</div>
            <div className="detail-content">{r.explanation}</div>
          </div>
        )}

        {r.key_points && r.key_points.length > 0 && (
          <div className="detail-section">
            <div className="detail-label">关键知识点</div>
            <div className="key-points-list">
              {r.key_points.map((kp, i) => (
                <Tag key={i} color="geekblue">{kp}</Tag>
              ))}
            </div>
          </div>
        )}

        <div className="record-actions">
          <Popconfirm title="确定删除这条记录？" onConfirm={() => handleDelete(r.id)} okText="删除" cancelText="取消">
            <Button type="text" danger icon={<DeleteOutlined />} size="small">删除</Button>
          </Popconfirm>
        </div>
      </div>
    ),
  }));

  return (
    <div className="exercise-history-page">
      <div className="page-header">
        <h2>练习记录</h2>
        <p>查看你的所有习题练习历史和答题情况</p>
      </div>

      {stats && (
        <Row gutter={16} className="stats-row">
          <Col xs={12} sm={6}>
            <Card className="stat-card stat-total">
              <Statistic
                title="总练习数"
                value={stats.total}
                prefix={<BookOutlined />}
              />
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card className="stat-card stat-correct">
              <Statistic
                title="答对数"
                value={stats.correct}
                prefix={<CheckCircleFilled style={{ color: '#52c41a' }} />}
                valueStyle={{ color: '#52c41a' }}
              />
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card className="stat-card stat-wrong">
              <Statistic
                title="答错数"
                value={stats.wrong}
                prefix={<CloseCircleFilled style={{ color: '#ff4d4f' }} />}
                valueStyle={{ color: '#ff4d4f' }}
              />
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card className="stat-card stat-accuracy">
              <Statistic
                title="正确率"
                value={stats.accuracy}
                suffix="%"
                prefix={<AimOutlined />}
                valueStyle={{ color: stats.accuracy >= 60 ? '#52c41a' : '#ff4d4f' }}
              />
            </Card>
          </Col>
        </Row>
      )}

      {stats && stats.by_chapter && Object.keys(stats.by_chapter).length > 0 && (
        <Card className="chapter-stats-card" title={<><FireOutlined /> 各章节正确率</>} size="small">
          <div className="chapter-bars">
            {Object.entries(stats.by_chapter).map(([ch, data]) => {
              const pct = data.total > 0 ? Math.round(data.correct / data.total * 100) : 0;
              return (
                <div key={ch} className="chapter-bar-row">
                  <span className="chapter-bar-label">{chapterMap[ch] || ch}</span>
                  <div className="chapter-bar-track">
                    <div
                      className="chapter-bar-fill"
                      style={{ width: `${pct}%`, backgroundColor: pct >= 60 ? '#52c41a' : '#ff4d4f' }}
                    />
                  </div>
                  <span className="chapter-bar-pct">{pct}%</span>
                  <span className="chapter-bar-count">{data.correct}/{data.total}</span>
                </div>
              );
            })}
          </div>
        </Card>
      )}

      <Card className="filter-card">
        <div className="filter-bar">
          <Space wrap>
            <Select
              placeholder="筛选章节"
              allowClear
              style={{ width: 150 }}
              value={filterChapter || undefined}
              onChange={(v) => setFilterChapter(v || '')}
            >
              {Object.entries(chapterMap).map(([k, v]) => (
                <Option key={k} value={k}>{v}</Option>
              ))}
            </Select>
            <Select
              placeholder="题目类型"
              allowClear
              style={{ width: 120 }}
              value={filterType || undefined}
              onChange={(v) => setFilterType(v || '')}
            >
              <Option value="choice">选择题</Option>
              <Option value="short_answer">简答题</Option>
            </Select>
            <Select
              placeholder="答题结果"
              allowClear
              style={{ width: 120 }}
              value={filterCorrect !== '' ? filterCorrect : undefined}
              onChange={(v) => setFilterCorrect(v !== undefined ? v : '')}
            >
              <Option value="true">答对</Option>
              <Option value="false">答错</Option>
            </Select>
            <Tooltip title="刷新">
              <Button icon={<ReloadOutlined />} onClick={fetchData} />
            </Tooltip>
          </Space>
          <Popconfirm title="确定清空所有练习记录？" onConfirm={handleClearAll} okText="清空" cancelText="取消">
            <Button danger icon={<ClearOutlined />}>清空全部</Button>
          </Popconfirm>
        </div>
      </Card>

      <Spin spinning={loading}>
        {records.length > 0 ? (
          <Collapse
            className="records-collapse"
            accordion
            items={collapseItems}
          />
        ) : (
          <Card className="empty-card">
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={
                <span>
                  {filterChapter || filterType || filterCorrect !== ''
                    ? '没有符合筛选条件的记录'
                    : '还没有练习记录，去做几道题吧！'}
                </span>
              }
            >
              {!filterChapter && !filterType && filterCorrect === '' && (
                <Button type="primary" icon={<TrophyOutlined />}>
                  开始练习
                </Button>
              )}
            </Empty>
          </Card>
        )}
      </Spin>
    </div>
  );
};

export default ExerciseHistory;
