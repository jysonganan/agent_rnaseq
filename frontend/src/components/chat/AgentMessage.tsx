import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { cn } from "@/lib/utils"

// Allowed elements per safety_policy.md Rule 11.2 — blocks <script>, <iframe>, etc.
const ALLOWED_ELEMENTS = [
  "p", "br", "strong", "em", "code", "pre",
  "ul", "ol", "li", "blockquote", "h1", "h2", "h3", "h4",
  "table", "thead", "tbody", "tr", "th", "td", "a",
] as const

interface Props {
  content: string
}

export function AgentMessage({ content }: Props) {
  return (
    <div className="flex justify-start">
      <div className="max-w-[80%] rounded-2xl rounded-tl-sm border bg-card px-4 py-3 text-sm break-words">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          allowedElements={ALLOWED_ELEMENTS as unknown as string[]}
          components={{
            // Sanitize link hrefs — only https:// and mailto: are safe
            a: ({ href, children }) => {
              const safe = href?.startsWith("https://") || href?.startsWith("mailto:")
              if (!safe) return <span>{children}</span>
              return (
                <a
                  href={href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary underline underline-offset-2"
                >
                  {children}
                </a>
              )
            },
            // Inline vs block code — `inline` prop differentiates them in react-markdown v8
            code: ({ inline, className, children, ...props }) => {
              if (inline) {
                return (
                  <code
                    className="rounded bg-muted px-1 py-0.5 font-mono text-xs"
                    {...props}
                  >
                    {children}
                  </code>
                )
              }
              return (
                <pre className="my-2 overflow-x-auto rounded-md bg-muted p-3">
                  <code className={cn("font-mono text-xs", className)} {...props}>
                    {children}
                  </code>
                </pre>
              )
            },
            // Override <pre> to avoid double-wrapping from the code component above
            pre: ({ children }) => <>{children}</>,
            blockquote: ({ children }) => (
              <blockquote className="my-2 border-l-4 border-primary/30 pl-4 italic text-muted-foreground">
                {children}
              </blockquote>
            ),
            table: ({ children }) => (
              <div className="my-2 overflow-x-auto">
                <table className="w-full border-collapse text-sm">{children}</table>
              </div>
            ),
            th: ({ children }) => (
              <th className="border border-border bg-muted/50 px-3 py-1.5 text-left font-semibold">
                {children}
              </th>
            ),
            td: ({ children }) => (
              <td className="border border-border px-3 py-1.5">{children}</td>
            ),
            h1: ({ children }) => <h1 className="mt-3 mb-1 text-lg font-bold">{children}</h1>,
            h2: ({ children }) => <h2 className="mt-3 mb-1 text-base font-bold">{children}</h2>,
            h3: ({ children }) => <h3 className="mt-2 mb-1 text-sm font-bold">{children}</h3>,
            h4: ({ children }) => <h4 className="mt-2 mb-1 text-sm font-semibold">{children}</h4>,
            p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
            ul: ({ children }) => <ul className="my-1 ml-4 list-disc space-y-0.5">{children}</ul>,
            ol: ({ children }) => <ol className="my-1 ml-4 list-decimal space-y-0.5">{children}</ol>,
          }}
        >
          {content}
        </ReactMarkdown>
      </div>
    </div>
  )
}
