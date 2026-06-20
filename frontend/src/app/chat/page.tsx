import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export default function ChatPage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 p-8 bg-background">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="text-2xl">agent_rnaseq</CardTitle>
          <CardDescription>RNA-seq analysis pipeline agent</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <p className="text-sm text-muted-foreground">
            Describe your analysis in natural language to get started.
          </p>
          <div className="flex gap-2">
            <Button>New Analysis</Button>
            <Button variant="outline">View Runs</Button>
          </div>
          <Badge variant="secondary" className="w-fit">
            Scaffold ready — TASK_FE_01
          </Badge>
        </CardContent>
      </Card>
    </main>
  )
}
