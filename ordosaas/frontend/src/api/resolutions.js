import client from './client'

export const getResolution = (id) =>
  client.get(`/resolutions/${id}`).then((r) => r.data)

export const getGantt = (id, params) =>
  client.get(`/resolutions/${id}/gantt`, { params }).then((r) => r.data)

export const getJobInResolution = (resolutionId, jobId) =>
  client.get(`/resolutions/${resolutionId}/jobs/${jobId}`).then((r) => r.data)

export const cancelResolution = (id) =>
  client.post(`/resolutions/${id}/cancel`).then((r) => r.data)

export const deleteResolution = (id) =>
  client.delete(`/resolutions/${id}`).then((r) => r.data)
