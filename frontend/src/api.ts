import axios, { AxiosInstance } from 'axios';

export interface AuthPayload {
  email: string;
  password: string;
}

export interface User {
  uid: string;
  email: string;
  role: string;
  [key: string]: any;
}

// Create the axios instance with credentials enabled
const axiosInstance: AxiosInstance = axios.create({
  baseURL: '/v1/api',
  withCredentials: true, // <-- CRITICAL: This sends the HttpOnly cookie with every request
});

// Auth API
export const login = async (payload: AuthPayload): Promise<User> => {
  try {
    const { data } = await axiosInstance.post('/auth/login', payload);
    // The backend sets the cookie; we just return the user object
    return data.user;
  } catch (error) {
    throw error;
  }
};

export const logout = async (): Promise<void> => {
  try {
    await axiosInstance.post('/auth/logout');
  } catch (error) {
    throw error;
  }
};

export const checkAuth = async (): Promise<User> => {
  try {
    const { data } = await axiosInstance.get('/auth/check');
    return data.user;
  } catch (error) {
    throw error;
  }
};

// Chat API
export const sendChat = async (query: string, projectId: string): Promise<any> => {
  try {
    const { data } = await axiosInstance.post('/chat', {
      query: query,
      project_id: projectId,
    });
    return data;
  } catch (error) {
    throw error;
  }
};

// Projects API
export const getProjects = async (): Promise<any> => {
  try {
    const { data } = await axiosInstance.get('/projects');
    return data;
  } catch (error) {
    throw error;
  }
};

// Export the configured axios instance for use in other API calls
export { axiosInstance };
