import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createHashRouter, RouterProvider } from 'react-router-dom'
import './index.css'
import AppShell from './components/layout/AppShell'
import ProjectsLanding from './components/projects/ProjectsLanding'
import ProjectView from './components/project/ProjectView'
import WorkflowCanvas from './components/canvas/WorkflowCanvas'
import DecisionsView from './components/decisions/DecisionsView'
import AssetsView from './components/assets/AssetsView'
import KnowledgeView from './components/knowledge/KnowledgeView'
import DataEngineView from './components/dataeng/DataEngineView'
import GlobalSettingsView, { ProjectSettingsInShell } from './components/settings/GlobalSettingsView'

const router = createHashRouter([
  { path: '/', element: <ProjectsLanding /> },
  { path: '/settings', element: <GlobalSettingsView /> },
  {
    path: '/p/:projectId',
    element: <AppShell />,
    children: [
      { index: true, element: <ProjectView /> },
      { path: 'canvas', element: <WorkflowCanvas /> },
      { path: 'decisions', element: <DecisionsView /> },
      { path: 'data', element: <DataEngineView /> },
      { path: 'assets', element: <AssetsView /> },
      { path: 'knowledge', element: <KnowledgeView /> },
      { path: 'settings', element: <ProjectSettingsInShell /> },
    ],
  },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
)
