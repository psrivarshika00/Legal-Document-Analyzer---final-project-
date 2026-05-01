module.exports = {
  apps: [
    {
      name: 'legal-analyzer-frontend',
      script: 'npm',
      args: 'start',
      cwd: '/home/ubuntu/Legal-Document-Analyzer---final-project-/frontend',
      env: {
        NODE_ENV: 'production',
        NEXT_PUBLIC_API_URL: 'http://18.207.232.182:5001',
      },
    },
  ],
};
