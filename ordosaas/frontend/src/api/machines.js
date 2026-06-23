import client from './client'

export const listMachines = () => client.get('/machines').then((r) => r.data)

export const createMachine = (data) =>
  client.post('/machines', data).then((r) => r.data)

export const updateMachine = (id, data) =>
  client.patch(`/machines/${id}`, data).then((r) => r.data)

export const deleteMachine = (id) =>
  client.delete(`/machines/${id}`).then((r) => r.data)
