import client from './client'

export const login = (email, password, remember_me = false) =>
  client.post('/auth/login', { email, password, remember_me }).then((r) => r.data)

export const logout = () => client.post('/auth/logout').then((r) => r.data)

export const refresh = (refresh_token) =>
  client.post('/auth/refresh', { refresh_token }).then((r) => r.data)

export const forgotPassword = (email) =>
  client.post('/auth/forgot-password', { email }).then((r) => r.data)

export const resetPassword = (token, password) =>
  client.post('/auth/reset-password', { token, password }).then((r) => r.data)

export const acceptInvitation = (token, password, firstName, lastName) =>
  client
    .post('/auth/accept-invitation', {
      token,
      password,
      first_name: firstName,
      last_name: lastName,
    })
    .then((r) => r.data)
