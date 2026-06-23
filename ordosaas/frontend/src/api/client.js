import axios from 'axios'

import { useAuthStore } from '../stores/authStore'

const client = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
})

// Attach the bearer token from the Zustand store on every request.
client.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Normalise errors and handle 401 globally.
client.interceptors.response.use(
  (response) => response,
  (error) => {
    const { response } = error

    if (response?.status === 401) {
      useAuthStore.getState().logout()
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }

    const data = response?.data || {}
    const normalised = {
      message: data.message || error.message || 'Une erreur est survenue',
      error: data.error || 'error',
      detail: data.detail || {},
      status: response?.status,
    }
    return Promise.reject(normalised)
  },
)

export default client
