/**
 * The new-ticket form.
 *
 * The submit button stays disabled until the subject is chosen and the text has
 * content: the backend would reject it anyway, and a disabled button with the
 * reason in the markup is kinder than a round trip that ends in an error.
 */

export { FeedbackNew } from "./ui/FeedbackNew.tsx";