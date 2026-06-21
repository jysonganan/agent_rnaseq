import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MessageInput } from "../MessageInput"

describe("MessageInput", () => {
  it("calls onSubmit with trimmed value on Enter", async () => {
    const onSubmit = jest.fn()
    const onChange = jest.fn()
    render(
      <MessageInput
        value="hello world"
        onChange={onChange}
        onSubmit={onSubmit}
      />
    )
    const textarea = screen.getByLabelText("Message input")
    await userEvent.click(textarea)
    await userEvent.keyboard("{Enter}")
    expect(onSubmit).toHaveBeenCalledWith("hello world")
  })

  it("does not submit on Shift+Enter", async () => {
    const onSubmit = jest.fn()
    render(
      <MessageInput value="hello" onChange={jest.fn()} onSubmit={onSubmit} />
    )
    const textarea = screen.getByLabelText("Message input")
    await userEvent.click(textarea)
    await userEvent.keyboard("{Shift>}{Enter}{/Shift}")
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it("does not submit when value is empty", async () => {
    const onSubmit = jest.fn()
    render(
      <MessageInput value="" onChange={jest.fn()} onSubmit={onSubmit} />
    )
    const textarea = screen.getByLabelText("Message input")
    await userEvent.click(textarea)
    await userEvent.keyboard("{Enter}")
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it("does not submit when value is whitespace only", async () => {
    const onSubmit = jest.fn()
    render(
      <MessageInput value="   " onChange={jest.fn()} onSubmit={onSubmit} />
    )
    const textarea = screen.getByLabelText("Message input")
    await userEvent.click(textarea)
    await userEvent.keyboard("{Enter}")
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it("textarea is disabled when disabled=true", () => {
    render(
      <MessageInput
        value="test"
        onChange={jest.fn()}
        onSubmit={jest.fn()}
        disabled
      />
    )
    expect(screen.getByLabelText("Message input")).toBeDisabled()
  })

  it("send button is disabled when disabled=true", () => {
    render(
      <MessageInput
        value="test"
        onChange={jest.fn()}
        onSubmit={jest.fn()}
        disabled
      />
    )
    expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled()
  })

  it("send button is disabled when value is empty", () => {
    render(
      <MessageInput value="" onChange={jest.fn()} onSubmit={jest.fn()} />
    )
    expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled()
  })

  it("calls onSubmit on button click", async () => {
    const onSubmit = jest.fn()
    render(
      <MessageInput
        value="click submit"
        onChange={jest.fn()}
        onSubmit={onSubmit}
      />
    )
    await userEvent.click(screen.getByRole("button", { name: "Send message" }))
    expect(onSubmit).toHaveBeenCalledWith("click submit")
  })

  it("trims whitespace before calling onSubmit", async () => {
    const onSubmit = jest.fn()
    render(
      <MessageInput
        value="  trimmed  "
        onChange={jest.fn()}
        onSubmit={onSubmit}
      />
    )
    await userEvent.click(screen.getByRole("button", { name: "Send message" }))
    expect(onSubmit).toHaveBeenCalledWith("trimmed")
  })
})
