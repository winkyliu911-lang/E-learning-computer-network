import React, { useState } from 'react';
import {
  Card,
  Button,
  Radio,
  Input,
  Space,
  Row,
  Col,
  message,
  Spin,
  Tag,
  Divider,
  Select
} from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  BulbOutlined,
  ThunderboltOutlined
} from '@ant-design/icons';
import './ExercisePractice.css';

const ExercisePractice = () => {
  const [chapter, setChapter] = useState(''); // 章节选择
  const [questionType, setQuestionType] = useState(''); // choice 或 short_answer
  const [difficulty, setDifficulty] = useState('medium'); // easy, medium, hard
  const [loading, setLoading] = useState(false);
  const [exercise, setExercise] = useState(null);
  const [userAnswer, setUserAnswer] = useState('');
  const [feedback, setFeedback] = useState(null);
  const [submitted, setSubmitted] = useState(false);
  const [exerciseHistory, setExerciseHistory] = useState([]);
  const [generatedQuestionIds, setGeneratedQuestionIds] = useState(new Set()); // 追踪已生成的题目
  // 知识库为服务端内置，前端不允许上传

  const chapters = [
    { label: '物理层', value: 'physical_layer' },
    { label: '数据链路层', value: 'data_link_layer' },
    { label: '网络层', value: 'network_layer' },
    { label: '传输层', value: 'transport_layer' },
    { label: '应用层', value: 'application_layer' }
  ];

  // 获取用户 token
  const getToken = () => localStorage.getItem('access_token');

  // 生成新题目
  const generateExercise = async () => {
    if (!chapter) {
      message.warning('请先选择章节');
      return;
    }
    if (!questionType) {
      message.warning('请先选择题目类型');
      return;
    }

    try {
      setLoading(true);
      setSubmitted(false);
      setUserAnswer('');
      setFeedback(null);

      // 向后端发送已生成题目的历史，用于去重
      const response = await fetch('http://localhost:8000/api/exercises/generate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${getToken()}`
        },
        body: JSON.stringify({
          chapter: chapter,
          question_type: questionType,
          difficulty: difficulty,
          previous_questions: Array.from(generatedQuestionIds) // 传送已生成题目列表
        })
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || '生成题目失败');
      }

      const data = await response.json();
      
      if (!data.exercise) {
        throw new Error('响应数据格式错误：缺少 exercise 字段');
      }
      
      setExercise(data.exercise);
      
      // 使用返回的哈希值来追踪这个题目（防止重复生成）
      if (data.question_hash) {
        setGeneratedQuestionIds(prev => new Set(prev).add(data.question_hash));
      }
      
      message.success('✨ 题目已生成！');
    } catch (error) {
      console.error('生成题目失败:', error);
      message.error('生成题目失败: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  // 知识库为服务端内置，前端无上传或初始化功能

  // 提交答案
  const submitAnswer = async () => {
    if (!userAnswer.trim()) {
      message.warning('请输入或选择答案');
      return;
    }

    try {
      setLoading(true);

      const response = await fetch('http://localhost:8000/api/exercises/submit', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${getToken()}`
        },
        body: JSON.stringify({
          question: exercise.question,
          question_type: questionType,
          user_answer: userAnswer,
          correct_answer: exercise.correct_answer,
          chapter: chapter,
          difficulty: difficulty,
          options: exercise.options,
          explanation: exercise.explanation,
          key_points: exercise.key_points,
          sample_answer: exercise.sample_answer,
        })
      });

      if (!response.ok) {
        throw new Error('提交答案失败');
      }

      const data = await response.json();
      setFeedback(data);
      setSubmitted(true);

      // 添加到历史记录
      setExerciseHistory([
        ...exerciseHistory,
        {
          id: Date.now(),
          question: exercise.question,
          type: questionType,
          chapter: chapter,
          userAnswer: userAnswer,
          isCorrect: data.is_correct || data.score >= 60,
          feedback: data.feedback
        }
      ]);

      message.success('✅ 答案已提交，已生成反馈');
    } catch (error) {
      console.error('提交答案失败:', error);
      message.error('提交答案失败: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  const renderExercise = () => {
    if (loading && !exercise) {
      return (
        <div className="exercise-loading">
          <Spin size="large" tip="正在为你生成新题目..." />
          <p className="loading-text">系统正在调用 RAG 检索知识库并生成题目，请稍候...</p>
        </div>
      );
    }

    if (!exercise) {
      return (
        <div className="exercise-empty">
          <BulbOutlined className="empty-icon" />
          <p>选择章节和题目类型，点击"生成题目"开始练习</p>
        </div>
      );
    }

    return (
      <div className="exercise-content">
        <div className="question-section">
          <h3>题目</h3>
          <p className="question-text">{exercise.question}</p>

          {questionType === 'choice' && exercise.options && (
            <div className="options-section">
              <h4>选择答案：</h4>
              <Radio.Group
                value={userAnswer}
                onChange={(e) => setUserAnswer(e.target.value)}
                disabled={submitted}
              >
                <Space direction="vertical" style={{ width: '100%' }}>
                  {exercise.options.map((option, idx) => (
                    <Radio key={idx} value={String.fromCharCode(65 + idx)}>
                      <span className="option-text">
                        {String.fromCharCode(65 + idx)}. {option.replace(/^[A-Da-d][.、．:\s]+/, '')}
                      </span>
                    </Radio>
                  ))}
                </Space>
              </Radio.Group>
            </div>
          )}

          {questionType === 'short_answer' && (
            <div className="answer-section">
              <h4>输入答案：</h4>
              <Input.TextArea
                rows={5}
                placeholder="请输入你的答案..."
                value={userAnswer}
                onChange={(e) => setUserAnswer(e.target.value)}
                disabled={submitted}
                className="answer-input"
              />
            </div>
          )}
        </div>

        {/* 反馈部分 */}
        {feedback && submitted && (
          <div className={`feedback-section ${feedback.is_correct ? 'correct' : 'incorrect'}`}>
            <div className="feedback-header">
              {feedback.is_correct ? (
                <>
                  <CheckCircleOutlined className="success-icon" />
                  <span>✅ 回答正确！</span>
                </>
              ) : (
                <>
                  <CloseCircleOutlined className="error-icon" />
                  <span>❌ 回答有误</span>
                </>
              )}
            </div>

            {feedback.feedback && (
              <div className="feedback-text">
                <h4>📢 反馈</h4>
                <p>{feedback.feedback}</p>
              </div>
            )}

            {feedback.score !== undefined && (
              <div className="score-display">
                <span className="score-label">得分：</span>
                <span className={`score-value ${feedback.score >= 60 ? 'high' : 'low'}`}>
                  {feedback.score}/100
                </span>
              </div>
            )}

            {questionType === 'choice' && feedback.correct_answer && (
              <div className="correct-answer">
                <h4>✓ 标准答案</h4>
                <p>{feedback.correct_answer}</p>
              </div>
            )}

            {feedback.explanation && (
              <div className="explanation">
                <h4>💡 解析</h4>
                <p>{feedback.explanation}</p>
              </div>
            )}

            {feedback.key_points && (
              <div className="key-points">
                <h4>🎯 关键点</h4>
                <div className="points-list">
                  {feedback.key_points.map((point, idx) => (
                    <Tag key={idx} color="blue">
                      {point}
                    </Tag>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* 操作按钮 */}
        <div className="exercise-actions">
          {!submitted ? (
            <Button
              type="primary"
              size="large"
              onClick={submitAnswer}
              loading={loading}
              icon={<ThunderboltOutlined />}
              disabled={!userAnswer.trim()}
            >
              提交答案
            </Button>
          ) : (
            <Button
              type="primary"
              size="large"
              onClick={generateExercise}
              loading={loading}
              icon={<BulbOutlined />}
            >
              下一题
            </Button>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="exercise-practice">
      <Row gutter={24}>
        {/* 左侧：题目展示区 */}
        <Col xs={24} lg={16}>
          <Card
            title={
              <div className="card-title">
                <span>计算机网络习题练习</span>
              </div>
            }
            className="exercise-card"
            loading={loading}
          >
            {renderExercise()}
          </Card>
        </Col>

        {/* 右侧：控制面板 */}
        <Col xs={24} lg={8}>
          <Card
            title="控制面板"
            className="control-panel"
          >
            <Space direction="vertical" style={{ width: '100%' }} size="large">
              {/* 章节选择 - 随时可修改 */}
              <div className="control-group">
                <label>选择章节</label>
                <Select
                  placeholder="请选择章节"
                  value={chapter || undefined}
                  onChange={setChapter}
                  options={chapters}
                  style={{ width: '100%' }}
                />
              </div>

              {/* 题目类型选择 - 随时可修改 */}
              <div className="control-group">
                <label>题目类型</label>
                <Select
                  placeholder="请选择题目类型"
                  value={questionType || undefined}
                  onChange={setQuestionType}
                  options={[
                    { label: '选择题', value: 'choice' },
                    { label: '简答题', value: 'short_answer' }
                  ]}
                  style={{ width: '100%' }}
                />
              </div>

              {/* 难度选择 - 随时可修改 */}
              <div className="control-group">
                <label>难度级别</label>
                <Select
                  value={difficulty}
                  onChange={setDifficulty}
                  options={[
                    { label: '🟢 简单', value: 'easy' },
                    { label: '🟡 中等', value: 'medium' },
                    { label: '🔴 困难', value: 'hard' }
                  ]}
                  style={{ width: '100%' }}
                />
              </div>

              <Divider />

              {/* 生成题目按钮 */}
              <Button
                type="primary"
                size="large"
                block
                onClick={generateExercise}
                loading={loading}
                icon={<BulbOutlined />}
                disabled={!chapter || !questionType}
              >
                生成新题目
              </Button>

              <Divider />
              {/* 知识库为服务端内置，前端不提供上传/初始化功能 */}
              {/* 统计信息 */}
              <div className="stats">
                <h4>📊 练习统计</h4>
                <div className="stat-item">
                  <span>总题数：</span>
                  <span className="stat-value">{exerciseHistory.length}</span>
                </div>
                <div className="stat-item">
                  <span>正确数：</span>
                  <span className="stat-value success">
                    {exerciseHistory.filter(h => h.isCorrect).length}
                  </span>
                </div>
                <div className="stat-item">
                  <span>错误数：</span>
                  <span className="stat-value error">
                    {exerciseHistory.filter(h => !h.isCorrect).length}
                  </span>
                </div>
                {exerciseHistory.length > 0 && (
                  <div className="stat-item">
                    <span>正确率：</span>
                    <span className="stat-value">
                      {(
                        (exerciseHistory.filter(h => h.isCorrect).length / exerciseHistory.length) * 100
                      ).toFixed(1)}%
                    </span>
                  </div>
                )}
              </div>

              <Divider />

              {/* 学习建议 */}
              <div className="tips">
                <h4>💡 学习建议</h4>
                <ul>
                  <li>先做简单题目，逐步提升难度</li>
                  <li>注意阅读反馈和解析</li>
                  <li>重复练习容易出错的知识点</li>
                  <li>结合教科书进行学习</li>
                </ul>
              </div>
            </Space>
          </Card>
        </Col>
      </Row>

      {/* 练习历史 */}
      {exerciseHistory.length > 0 && (
        <Card
          title="📜 练习历史"
          className="history-card"
          style={{ marginTop: 24 }}
        >
          <div className="history-list">
            {exerciseHistory.map((item, idx) => {
              const chapterMap = {
                'physical_layer': '物理层',
                'data_link_layer': '数据链路层',
                'network_layer': '网络层',
                'transport_layer': '传输层',
                'application_layer': '应用层'
              };
              return (
                <div key={item.id} className="history-item">
                  <div className="item-header">
                    <span className="item-index">第 {idx + 1} 题</span>
                    <Tag color={item.isCorrect ? 'green' : 'red'}>
                      {item.isCorrect ? '✅ 正确' : '❌ 错误'}
                    </Tag>
                    <Tag color="blue">
                      {item.type === 'choice' ? '选择题' : '简答题'}
                    </Tag>
                    <Tag color="purple">
                      {chapterMap[item.chapter] || item.chapter}
                    </Tag>
                  </div>
                  <p className="item-question">{item.question}</p>
                  <p className="item-answer">你的答案：{item.userAnswer}</p>
                </div>
              );
            })}
          </div>
        </Card>
      )}
    </div>
  );
};

export default ExercisePractice;
