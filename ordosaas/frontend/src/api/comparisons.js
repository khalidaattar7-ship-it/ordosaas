import client from './client'

export const createComparison = (resolutionAId, resolutionBId) =>
  client
    .post('/comparisons', {
      resolution_a_id: resolutionAId,
      resolution_b_id: resolutionBId,
    })
    .then((r) => r.data)
