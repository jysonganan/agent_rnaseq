import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { conversationsApi } from "@/lib/api"

interface ListParams {
  limit?: number
  offset?: number
}

export const conversationKeys = {
  all: () => ["conversations"] as const,
  list: (params?: ListParams) => ["conversations", "list", params] as const,
  detail: (id: string) => ["conversations", id] as const,
  messages: (id: string, params?: ListParams) =>
    ["conversations", id, "messages", params] as const,
}

export function useConversations(params?: ListParams) {
  return useQuery({
    queryKey: conversationKeys.list(params),
    queryFn: () => conversationsApi.list(params),
  })
}

export function useConversation(id: string) {
  return useQuery({
    queryKey: conversationKeys.detail(id),
    queryFn: () => conversationsApi.get(id),
    enabled: Boolean(id),
  })
}

export function useConversationMessages(id: string, params?: ListParams) {
  return useQuery({
    queryKey: conversationKeys.messages(id, params),
    queryFn: () => conversationsApi.getMessages(id, params),
    enabled: Boolean(id),
  })
}

export function useCreateConversation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (title?: string) => conversationsApi.create(title),
    onSuccess: () => qc.invalidateQueries({ queryKey: conversationKeys.all() }),
  })
}

export function useSendMessage(conversationId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (content: string) =>
      conversationsApi.sendMessage(conversationId, content),
    onSuccess: () =>
      qc.invalidateQueries({
        queryKey: conversationKeys.messages(conversationId),
      }),
  })
}

export function useDeleteConversation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => conversationsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: conversationKeys.all() }),
  })
}
