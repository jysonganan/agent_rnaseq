import { render, screen } from "@testing-library/react"
import { AgentMessage } from "../AgentMessage"

describe("AgentMessage", () => {
  it("renders bold text", () => {
    render(<AgentMessage content="**bold**" />)
    expect(screen.getByText("bold").tagName).toBe("STRONG")
  })

  it("renders italic text", () => {
    render(<AgentMessage content="*italic*" />)
    expect(screen.getByText("italic").tagName).toBe("EM")
  })

  it("renders inline code", () => {
    render(<AgentMessage content="`code`" />)
    expect(screen.getByText("code").tagName).toBe("CODE")
  })

  it("renders unordered list", () => {
    render(<AgentMessage content={"- item one\n- item two"} />)
    const ul = document.querySelector("ul")
    expect(ul).not.toBeNull()
    expect(ul?.textContent).toContain("item one")
    expect(ul?.textContent).toContain("item two")
  })

  it("renders a GFM table", () => {
    const md = "| A | B |\n|---|---|\n| 1 | 2 |"
    render(<AgentMessage content={md} />)
    expect(document.querySelector("table")).not.toBeNull()
    expect(screen.getByText("A")).toBeInTheDocument()
  })

  it("blocks <script> tags in Markdown content", () => {
    render(<AgentMessage content="<script>alert('xss')</script>safe text" />)
    expect(document.querySelector("script")).toBeNull()
    // The text inside the script is stripped along with the tag
  })

  it("blocks <iframe> tags in Markdown content", () => {
    render(<AgentMessage content='<iframe src="evil.com"></iframe>' />)
    expect(document.querySelector("iframe")).toBeNull()
  })

  it("renders https:// links as anchors with rel=noopener", () => {
    render(<AgentMessage content="[safe](https://example.com)" />)
    const link = screen.getByRole("link", { name: "safe" })
    expect(link).toHaveAttribute("href", "https://example.com")
    expect(link).toHaveAttribute("target", "_blank")
    expect(link).toHaveAttribute("rel", "noopener noreferrer")
  })

  it("renders mailto: links as anchors", () => {
    render(<AgentMessage content="[mail](mailto:a@b.com)" />)
    const link = screen.getByRole("link", { name: "mail" })
    expect(link).toHaveAttribute("href", "mailto:a@b.com")
  })

  it("renders unsafe hrefs as plain spans (no link)", () => {
    render(<AgentMessage content="[bad](javascript:alert('xss'))" />)
    expect(screen.queryByRole("link")).toBeNull()
    expect(screen.getByText("bad")).toBeInTheDocument()
  })
})
