interface ErrorStateProps {
  message: string
}

export function ErrorState({ message }: ErrorStateProps) {
  return (
    <div className="rounded-2xl border border-danger-border bg-danger-bg px-4 py-2 text-sm text-danger transition-colors duration-300">
      {message}
    </div>
  )
}
