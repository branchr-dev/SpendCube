import { Routes, Route, Navigate } from 'react-router-dom'
import ProtectedRoute from '@/components/ProtectedRoute'
import Layout from '@/components/Layout'
import LoginPage from '@/pages/auth/LoginPage'
import EngagementListPage from '@/pages/engagements/EngagementListPage'
import NewEngagementPage from '@/pages/engagements/NewEngagementPage'
import UploadPage from '@/pages/ingest/UploadPage'

function PlaceholderPage({ title }: { title: string }) {
  return <div className="p-6 text-muted-foreground">{title}</div>
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<Navigate to="/engagements" replace />} />

      <Route element={<ProtectedRoute />}>
        <Route path="/engagements" element={<EngagementListPage />} />
        <Route path="/engagements/new" element={<NewEngagementPage />} />
        <Route path="/engagements/:id" element={<Layout />}>
          <Route index element={<Navigate to="overview" replace />} />
          <Route path="overview" element={<PlaceholderPage title="Spend Overview" />} />
          <Route path="category" element={<PlaceholderPage title="Category Deep Dive" />} />
          <Route path="supplier" element={<PlaceholderPage title="Supplier Deep Dive" />} />
          <Route path="payment-terms" element={<PlaceholderPage title="Payment Terms" />} />
          <Route path="quality" element={<PlaceholderPage title="Data Quality" />} />
          <Route path="recommendations" element={<PlaceholderPage title="Recommendations" />} />
          <Route path="upload" element={<UploadPage />} />
          <Route path="admin/review" element={<PlaceholderPage title="Review Workstation" />} />
        </Route>
      </Route>
    </Routes>
  )
}
