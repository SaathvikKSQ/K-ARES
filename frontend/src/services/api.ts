import axios from "axios";

/** Typed Axios client for the K-AERS API. Base URL is env-overridable. */
export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? "/api/v1",
  withCredentials: true, // session cookie auth
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    // Normalize API errors into the documented envelope when available.
    if (error.response?.data?.error) {
      return Promise.reject(error.response.data.error);
    }
    return Promise.reject(error);
  },
);
