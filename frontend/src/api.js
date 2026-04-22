import axios from 'axios';

const API_BASE_URL = 'http://localhost:8000/api';

const api = axios.create({
  baseURL: API_BASE_URL,
});

const refreshApi = axios.create({
  baseURL: API_BASE_URL,
});

let refreshPromise = null;

const refreshAccessToken = async () => {
  const refreshToken = localStorage.getItem('refresh_token');
  if (!refreshToken) {
    throw new Error('missing refresh token');
  }

  const response = await refreshApi.post('/auth/refresh', null, {
    headers: {
      Authorization: `Bearer ${refreshToken}`,
    },
  });

  const newAccessToken = response?.data?.access_token;
  if (!newAccessToken) {
    throw new Error('missing access token');
  }

  localStorage.setItem('access_token', newAccessToken);
  return newAccessToken;
};

// 添加请求拦截器，自动添加token
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// 添加响应拦截器，统一处理 token 过期
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const status = error?.response?.status;
    const errorText = (error?.response?.data?.error || '').toLowerCase();
    const isTokenExpired = status === 401 && errorText.includes('token expired');
    const originalRequest = error?.config || {};

    if (isTokenExpired && !originalRequest._retry) {
      originalRequest._retry = true;

      try {
        if (!refreshPromise) {
          refreshPromise = refreshAccessToken().finally(() => {
            refreshPromise = null;
          });
        }

        const newAccessToken = await refreshPromise;
        originalRequest.headers = {
          ...(originalRequest.headers || {}),
          Authorization: `Bearer ${newAccessToken}`,
        };
        return api(originalRequest);
      } catch (refreshError) {
        return Promise.reject(error);
      }
    }

    return Promise.reject(error);
  }
);

// 认证相关
export const authAPI = {
  register: (username, email, password) =>
    api.post('/auth/register', { username, email, password }),
  login: (username, password) =>
    api.post('/auth/login', { username, password }),
  refresh: () => {
    const refreshToken = localStorage.getItem('refresh_token');
    return refreshApi.post('/auth/refresh', null, {
      headers: {
        Authorization: `Bearer ${refreshToken}`,
      },
    });
  },
};

// 课程视频相关
export const videoAPI = {
  getAll: (category) =>
    api.get('/videos', { params: { category } }),
  getById: (id) =>
    api.get(`/videos/${id}`),
  create: (data) =>
    api.post('/videos', data),
};

// 课本相关
export const textbookAPI = {
  getAll: (category) =>
    api.get('/textbooks', { params: { category } }),
  getById: (id) =>
    api.get(`/textbooks/${id}`),
  create: (data) =>
    api.post('/textbooks', data),
};

// 聊天相关
export const chatAPI = {
  create: (question, files, historyMessages = [], sessionId = '') => {
    const formData = new FormData();
    formData.append('question', question);
    formData.append('history_messages', JSON.stringify(Array.isArray(historyMessages) ? historyMessages : []));
    if (sessionId) {
      formData.append('session_id', sessionId);
    }
    if (Array.isArray(files) && files.length > 0) {
      files.forEach((file) => formData.append('files', file));
    } else if (files) {
      formData.append('files', files);
    }
    return api.post('/chat', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  getHistory: () =>
    api.get('/chat/history'),
  getById: (id) =>
    api.get(`/chat/${id}`),
  deleteHistory: (id) =>
    api.delete(`/chat/history/${id}`),
  deleteSessionHistory: (sessionId) =>
    api.delete(`/chat/history/session/${encodeURIComponent(sessionId)}`),
  deleteAllHistory: () =>
    api.delete('/chat/history'),
};

// RAG 管理相关
export const ragAPI = {
  uploadDocuments: (files) => {
    const fd = new FormData();
    files.forEach((f) => fd.append('files', f));
    return api.post('/rag/upload-documents', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  initFromServerData: () => api.post('/rag/init'),
  stats: () => api.get('/rag/stats'),
};

// 习题练习记录相关
export const exerciseAPI = {
  getHistory: (params) =>
    api.get('/exercises/history', { params }),
  getStats: () =>
    api.get('/exercises/stats'),
  deleteRecord: (id) =>
    api.delete(`/exercises/history/${id}`),
  clearAll: () =>
    api.delete('/exercises/history'),
};

// 笔记相关
export const noteAPI = {
  create: (data) =>
    api.post('/notes', data),
  getAll: (params) =>
    api.get('/notes', { params }),
  update: (id, data) =>
    api.put(`/notes/${id}`, data),
  delete: (id) =>
    api.delete(`/notes/${id}`),
};

export default api;
