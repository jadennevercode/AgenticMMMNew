import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createHashRouter, RouterProvider } from 'react-router-dom'
import './index.css'
import AppShell from './components/layout/AppShell'
import ProjectView from './components/project/ProjectView'
import WorkflowCanvas from './components/canvas/WorkflowCanvas'
import DecisionsView from './components/decisions/DecisionsView'
import AssetsView from './components/assets/AssetsView'
import KnowledgeView from './components/knowledge/KnowledgeView'

const router = createHashRouter([
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <ProjectView /> },
      { path: 'canvas', element: <WorkflowCanvas /> },
      { path: 'decisions', element: <DecisionsView /> },
      { path: 'assets', element: <AssetsView /> },
      { path: 'knowledge', element: <KnowledgeView /> },
    ],
  },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
)
