export function ThinkingIndicator() {
  return (
    <div className="flex justify-start">
      <div className="flex items-center gap-1 rounded-2xl rounded-tl-sm border bg-card px-4 py-3">
        <span
          className="h-2 w-2 rounded-full bg-muted-foreground animate-bounce"
          style={{ animationDelay: "-0.3s" }}
        />
        <span
          className="h-2 w-2 rounded-full bg-muted-foreground animate-bounce"
          style={{ animationDelay: "-0.15s" }}
        />
        <span className="h-2 w-2 rounded-full bg-muted-foreground animate-bounce" />
      </div>
    </div>
  )
}
