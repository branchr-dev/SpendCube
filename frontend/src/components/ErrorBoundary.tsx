import { Component, ErrorInfo, ReactNode } from 'react'
import { AlertCircle } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error(error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="max-w-md mx-auto mt-16">
          <Card>
            <CardContent className="flex flex-col items-center gap-4 pt-8 pb-8">
              <AlertCircle className="h-8 w-8 text-destructive" />
              <h3 className="font-semibold text-lg">Something went wrong</h3>
              <p className="text-xs font-mono text-muted-foreground break-all text-center">
                {this.state.error?.message}
              </p>
              <Button onClick={() => window.location.reload()}>Reload page</Button>
            </CardContent>
          </Card>
        </div>
      )
    }

    return this.props.children
  }
}
