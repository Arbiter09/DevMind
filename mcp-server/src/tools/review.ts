import { z } from "zod";
import { githubPost } from "../github.js";

export const postReviewCommentSchema = z.object({
  pr_number: z.number().int().positive().describe("Pull request number"),
  repo: z.string().describe("Repository in owner/repo format"),
  body: z.string().describe("Markdown-formatted review body"),
  event: z
    .enum(["APPROVE", "REQUEST_CHANGES", "COMMENT"])
    .default("COMMENT")
    .describe("Review event type"),
});

export async function postReviewComment(
  args: z.infer<typeof postReviewCommentSchema>
): Promise<string> {
  const { pr_number, repo, body, event } = args;
  const data = await githubPost(`/repos/${repo}/pulls/${pr_number}/reviews`, {
    body,
    event,
    comments: [],
  });
  return JSON.stringify({ id: data.id, state: data.state, html_url: data.html_url }, null, 2);
}
