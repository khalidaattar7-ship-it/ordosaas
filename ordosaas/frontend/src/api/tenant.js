import client from './client'

export const getTenant = () => client.get('/tenant').then((r) => r.data)

export const updateTenant = (data) =>
  client.patch('/tenant', data).then((r) => r.data)

export const listUsers = (params) =>
  client.get('/users', { params }).then((r) => r.data)

export const getMe = () => client.get('/users/me').then((r) => r.data)

export const inviteUser = (email, role) =>
  client.post('/users/invite', { email, role }).then((r) => r.data)

export const patchUser = (userId, data) =>
  client.patch(`/users/${userId}`, data).then((r) => r.data)

export const deleteUser = (userId) =>
  client.delete(`/users/${userId}`).then((r) => r.data)

export const listAuditLogs = (params) =>
  client.get('/audit-logs', { params }).then((r) => r.data)
