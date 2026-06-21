"use client"

import Link from "next/link"
import { useRouter } from "next/navigation"
import {
  FlaskConical,
  Globe,
  LogOut,
  MessageSquare,
  Play,
  PlusCircle,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { NavLink } from "./NavLink"
import { useConversations, useCreateConversation } from "@/hooks/useConversations"
import { useAuth } from "@/hooks/useAuth"

interface SidebarContentProps {
  /** Called after a navigation action so mobile sheets can close. */
  onNavigate?: () => void
}

export function SidebarContent({ onNavigate }: SidebarContentProps) {
  const router = useRouter()
  const { clearApiKey } = useAuth()
  const { data } = useConversations({ limit: 20 })
  const createConversation = useCreateConversation()

  async function handleNewChat() {
    const convo = await createConversation.mutateAsync(undefined)
    onNavigate?.()
    router.push(`/chat/${convo.id}`)
  }

  function handleSignOut() {
    clearApiKey()
    onNavigate?.()
    router.push("/")
  }

  return (
    <div className="flex flex-col h-full">
      {/* Branding */}
      <div className="flex items-center gap-2 px-4 py-4 border-b shrink-0">
        <FlaskConical className="h-5 w-5 text-primary shrink-0" />
        <span className="font-semibold text-sm truncate">agent_rnaseq</span>
      </div>

      {/* New Chat */}
      <div className="px-3 py-3 shrink-0">
        <Button
          className="w-full"
          size="sm"
          onClick={handleNewChat}
          disabled={createConversation.isPending}
        >
          <PlusCircle className="mr-2 h-4 w-4" />
          New Chat
        </Button>
      </div>

      {/* Recent conversations */}
      <div className="px-4 pb-1 shrink-0">
        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          Recent Chats
        </p>
      </div>
      <ScrollArea className="flex-1 px-2">
        <div className="flex flex-col gap-0.5 pb-2">
          {data?.conversations.map((conv) => (
            <Link
              key={conv.id}
              href={`/chat/${conv.id}`}
              onClick={onNavigate}
              className="block rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground truncate transition-colors"
              title={conv.title}
            >
              {conv.title}
            </Link>
          ))}
          {!data?.conversations.length && (
            <p className="px-3 py-2 text-xs text-muted-foreground">
              No conversations yet.
            </p>
          )}
        </div>
      </ScrollArea>

      <Separator />

      {/* Primary nav */}
      <nav className="px-2 py-2 flex flex-col gap-1 shrink-0">
        <NavLink href="/chat">
          <MessageSquare className="h-4 w-4 shrink-0" />
          Chat
        </NavLink>
        <NavLink href="/runs">
          <Play className="h-4 w-4 shrink-0" />
          Runs
        </NavLink>
        <NavLink href="/browser">
          <Globe className="h-4 w-4 shrink-0" />
          Browser
        </NavLink>
      </nav>

      <Separator />

      {/* Sign out */}
      <div className="px-3 py-3 shrink-0">
        <Button
          variant="ghost"
          size="sm"
          className="w-full justify-start text-muted-foreground hover:text-foreground"
          onClick={handleSignOut}
        >
          <LogOut className="mr-2 h-4 w-4" />
          Sign out
        </Button>
      </div>
    </div>
  )
}

export function Sidebar() {
  return (
    <aside className="hidden md:flex flex-col w-60 border-r bg-card shrink-0 h-screen sticky top-0">
      <SidebarContent />
    </aside>
  )
}
