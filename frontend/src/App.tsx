import { Routes, Route, Navigate } from 'react-router-dom'
import ProtectedRoute from '@/components/ProtectedRoute'
import Layout from '@/components/Layout'
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
        <Route path="/engagements" element={<EngagementListPage />} />
        <Route path="/engagements/new" element={<NewEngagementPage />} />
        <Route path="/engagements/:id" element={<Layout />}>
          <Route index element={<Navigate to="overview" replace />} />
          <Route path="overview" element={<OverviewPage />} />
          <Route path="category" element={<CategoryPage />} />
          <Route path="supplier" element={<SupplierPage />} />
          <Route path="payment-terms" element={<PaymentTermsPage />} />
          <Route path="quality" element={<DataQualityPage />} />
          <Route path="recommendations" element={<RecommendationsPage />} />
          <Route path="upload" element={<UploadPage />} />
          <Route path="admin/review" element={<ReviewWorkstationPage />} />
        </Route>
      </Route>
    </Routes>
  )
}
