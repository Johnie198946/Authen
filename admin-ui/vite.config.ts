import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Microservice port mapping:
// auth:8001, sso:8002, user:8003, permission:8004,
// organization:8005, subscription:8006, admin:8007, gateway:8008

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // Health check (auth service 8001)
      '/health': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
      // Auth service (8001)
      '/api/v1/auth': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
      // Permission service (8004) - roles & permissions CRUD
      '/api/v1/roles': {
        target: 'http://localhost:8004',
        changeOrigin: true,
      },
      '/api/v1/permissions': {
        target: 'http://localhost:8004',
        changeOrigin: true,
      },
      // Organization service (8005)
      '/api/v1/organizations': {
        target: 'http://localhost:8005',
        changeOrigin: true,
      },
      // Subscription service (8006) - plans CRUD
      '/api/v1/subscriptions': {
        target: 'http://localhost:8006',
        changeOrigin: true,
      },
      // Admin service (8007)
      '/api/v1/admin': {
        target: 'http://localhost:8007',
        changeOrigin: true,
      },
      // User-scoped sub-routes need special handling:
      // /api/v1/users/:id/roles -> permission service (8004)
      // /api/v1/users/:id/permissions -> permission service (8004)
      // /api/v1/users/:id/subscription -> subscription service (8006)
      // /api/v1/users/* -> user service (8003)
      //
      // Vite proxy matches rules in order; more specific patterns must come first.
      // We use RegExp-based keys so that sub-resource routes hit the correct service.
      '^/api/v1/users/[^/]+/roles': {
        target: 'http://localhost:8004',
        changeOrigin: true,
      },
      '^/api/v1/users/[^/]+/permissions': {
        target: 'http://localhost:8004',
        changeOrigin: true,
      },
      '^/api/v1/users/[^/]+/subscription': {
        target: 'http://localhost:8006',
        changeOrigin: true,
      },
      '/api/v1/users': {
        target: 'http://localhost:8003',
        changeOrigin: true,
      },
    },
  },
})
