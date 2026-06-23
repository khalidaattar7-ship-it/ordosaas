import { create } from 'zustand'
import { persist } from 'zustand/middleware'

import * as authApi from '../api/auth'

export const useAuthStore = create(
  persist(
    (set, get) => ({
      user: null,
      token: null,
      refreshToken: null,
      isAuthenticated: false,

      // Store tokens + user from a TokenResponse.
      login: (tokenResponse) =>
        set({
          user: tokenResponse.user,
          token: tokenResponse.access_token,
          refreshToken: tokenResponse.refresh_token,
          isAuthenticated: true,
        }),

      logout: () =>
        set({
          user: null,
          token: null,
          refreshToken: null,
          isAuthenticated: false,
        }),

      // Refresh the access token using the stored refresh token.
      refreshTokens: async () => {
        const rt = get().refreshToken
        if (!rt) return
        const res = await authApi.refresh(rt)
        set({
          user: res.user,
          token: res.access_token,
          refreshToken: res.refresh_token,
          isAuthenticated: true,
        })
      },

      isAdmin: () => get().user?.role === 'admin',
      isPlanner: () => ['admin', 'planificateur'].includes(get().user?.role),
    }),
    {
      name: 'ordosaas-auth',
      partialize: (s) => ({
        user: s.user,
        token: s.token,
        refreshToken: s.refreshToken,
        isAuthenticated: s.isAuthenticated,
      }),
    },
  ),
)
