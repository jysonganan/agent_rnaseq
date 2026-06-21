interface Props {
  content: string
}

export function UserMessage({ content }: Props) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[70%] rounded-2xl rounded-tr-sm bg-muted px-4 py-3 text-sm whitespace-pre-wrap break-words">
        {content}
      </div>
    </div>
  )
}
