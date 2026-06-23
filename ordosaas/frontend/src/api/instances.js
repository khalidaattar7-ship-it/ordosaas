import client from './client'

export const listInstances = (params) =>
  client.get('/instances', { params }).then((r) => r.data)

export const importInstance = (formData) =>
  client
    .post('/instances/import', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    .then((r) => r.data)

export const getInstance = (id) =>
  client.get(`/instances/${id}`).then((r) => r.data)

export const listJobs = (instanceId, params) =>
  client.get(`/instances/${instanceId}/jobs`, { params }).then((r) => r.data)

export const patchJob = (instanceId, jobId, data) =>
  client.patch(`/instances/${instanceId}/jobs/${jobId}`, data).then((r) => r.data)

export const addJob = (instanceId, data) =>
  client.post(`/instances/${instanceId}/jobs`, data).then((r) => r.data)

export const deleteJob = (instanceId, jobId) =>
  client.delete(`/instances/${instanceId}/jobs/${jobId}`).then((r) => r.data)

export const deleteInstance = (id) =>
  client.delete(`/instances/${id}`).then((r) => r.data)

export const resolveInstance = (instanceId, config) =>
  client.post(`/instances/${instanceId}/resolve`, config).then((r) => r.data)
