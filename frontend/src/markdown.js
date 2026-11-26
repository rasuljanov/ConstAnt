import MarkdownIt from "markdown-it";

// Model output must not execute HTML or fetch remote images.
const markdown = new MarkdownIt({ html: false, breaks: true, linkify: false });
markdown.renderer.rules.image = (tokens, index) =>
  markdown.utils.escapeHtml(tokens[index].content || "[image omitted]");
markdown.renderer.rules.link_open = (tokens, index, options, env, renderer) => {
  tokens[index].attrSet("target", "_blank");
  tokens[index].attrSet("rel", "noopener noreferrer");
  return renderer.renderToken(tokens, index, options);
};

export function cleanAnswer(text) {
  return (text || "").replace(/\[selected\s+tables\]/gi, "").trim();
}

export function renderMarkdown(text) {
  return markdown.render(cleanAnswer(text));
}
