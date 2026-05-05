import { Routes, Route, Navigate } from 'react-router-dom'
import ProtectedRoute from '@/components/ProtectedRoute'
import Layout from '@/components/Layout'
import ErrorBoundary from '@/components/ErrorBoundary'
import LoginPage from '@/pages/auth/LoginPage'
import EngagementListPage from '@/pages/engagements/EngagementListPage'
import NewEngagementPage from '@/pages/engagements/NewEngagementPage'
import UploadPage from '@/pages/ingest/UploadPage'
import OverviewPage from '@/pages/dashboard/OverviewPage'
import CategoryPage from '@/pages/dashboard/CategoryPage'
import SupplierPage from '@/pages/dashboard/SupplierPage'
import PaymentTermsPage from '@/pages/dashboard/PaymentTermsPage'
import DataQualityPage from '@/pages/dashboard/DataQualityPage'
import RecommendationsPage from '@/pages/dashboard/RecommendationsPage'
import ReviewWorkstationPage from '@/pages/admin/ReviewWorkstationPage'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<Navigate to="/engagements" replace />} />

      <Route element={<ProtectedRoute />}>
        <Route path="/engagements" element={<ErrorBoundary><EngagementListPage /></ErrorBoundary>} />
        <Route path="/engagements/new" element={<ErrorBoundary><NewEngagementPage /></ErrorBoundary>} />
        <Route path="/engagements/:id" element={<Layout />}>
          <Route index element={<Navigate to="overview" replace />} />
          <Route path="overview" element={<ErrorBoundary><OverviewPage /></ErrorBoundary>} />
          <Route path="category" element={<ErrorBoundary><CategoryPage /></ErrorBoundary>} />
          <Route path="supplier" element={<ErrorBoundary><SupplierPage /></ErrorBoundary>} />
          <Route path="payment-terms" element={<ErrorBoundary><PaymentTermsPage /></ErrorBoundary>} />
          <Route path="quality" element={<ErrorBoundary><DataQualityPage /></ErrorBoundary>} />
          <Route path="recommendations" element={<ErrorBoundary><RecommendationsPage /></ErrorBoundary>} />
          <Route path="upload" element={<ErrorBoundary><UploadPage /></ErrorBoundary>} />
          <Route path="admin/review" element={<ErrorBoundary><ReviewWorkstationPage /></ErrorBoundary>} />
        </Route>
      </Route>
    </Routes>
  )
}
