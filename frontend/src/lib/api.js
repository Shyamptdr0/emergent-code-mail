import axios from "axios";

export const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

export const api = axios.create({
  baseURL: API,
  withCredentials: true,
});

// Global 401 handler — session expired → redirect to login
api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err?.response?.status === 401) {
      const path = window.location.pathname;
      if (path !== "/login" && path !== "/") {
        window.location.href = "/login";
      }
    }
    return Promise.reject(err);
  }
);



export const logout = async () => {
  try { await api.post("/auth/logout"); } catch (e) {}
  window.location.href = "/";
};
