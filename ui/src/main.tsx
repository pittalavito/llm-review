import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { createBrowserRouter, Navigate, RouterProvider } from 'react-router-dom';

// Global styles, section-specific last.
import './styles/variables.css';
import './styles/reset.css';
import './styles/layout.css';
import './styles/components.css';
import './styles/ping-chat.css';
import './styles/admin.css';
import './styles/paper.css';
import './styles/review-graph.css';
import './styles/agent-config.css';
import './styles/input-messages.css';
import './styles/prompts.css';
import './styles/run-flow.css';
import './styles/agent-table.css';
import './styles/run-insights.css';

import AppLayout from './layout/AppLayout';
import Admin from './sections/Admin';
import Paper from './sections/Paper';
import PingChat from './sections/PingChat';
import GraphReview from './sections/GraphReview';
import Prompts from './sections/Prompts';
import RunCompare from './sections/RunCompare';
import RunHistory from './sections/RunHistory';
import { applyTheme, getInitialTheme } from './components/ThemeToggle';

// Stamp the saved theme on <html> before the first paint (no theme flash).
applyTheme(getInitialTheme());

const router = createBrowserRouter(
  [
    {
      path: '/',
      element: <AppLayout />,
      children: [
        { index: true, element: <Navigate to="/ping-chat" replace /> },
        { path: 'admin', element: <Admin /> },
        { path: 'ping-chat', element: <PingChat /> },
        { path: 'paper', element: <Paper /> },
        { path: 'review-graph', element: <GraphReview /> },
        { path: 'review-graph/storico', element: <RunHistory /> },
        { path: 'review-graph/confronto', element: <RunCompare /> },
        { path: 'prompt', element: <Prompts /> },
        { path: '*', element: <Navigate to="/ping-chat" replace /> },
      ],
    },
  ],
);

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
);
