import axios from 'axios'
import { supabase } from './supabase'

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL as string,
})

api.interceptors.request.use(async (config) => {
  const { data } = await supabase.auth.getSession()
  if (data.session) {
    config.headers.Authorization = `Bearer ${data.session.access_token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    // Do not sign out or redirect here — ProtectedRoute handles session checks.
    // Redirecting on 401 causes an infinite loop when the backend is misconfigured.
    return Promise.reject(error)
  }
)
