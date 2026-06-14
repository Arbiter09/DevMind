import { z } from "zod";
import { githubRequest } from "../github.js";

export const readFileSchema = z.object({
  path: z.string().describe("File path in the repository"),
  repo: z.string().describe("Repository in owner/repo format"),
  ref: z.string().describe("Git SHA or branch name"),
});

export const getFileHistorySchema = z.object({
  path: z.string().describe("File path in the repository"),
  repo: z.string().describe("Repository in owner/repo format"),
  per_page: z.number().int().min(1).max(100).default(10).describe("Number of commits to return"),
});

export async function readFile(args: z.infer<typeof readFileSchema>): Promise<string> {
  const { path, repo, ref } = args;
  const raw = await githubRequest(
    `/repos/${repo}/contents/${path}?ref=${encodeURIComponent(ref)}`
  );

  if (typeof raw === "string") {
    return raw;
  }

  const data = raw as Record<string, unknown>;

  if (data.encoding === "base64" && typeof data.content === "string") {
    return Buffer.from(data.content.replace(/\n/g, ""), "base64").toString("utf-8");
  }

  if (typeof data.content === "string") {
    return data.content;
  }

  return JSON.stringify(data);
}

export async function getFileHistory(
  args: z.infer<typeof getFileHistorySchema>
): Promise<string> {
  const { path, repo, per_page } = args;
  const commits = await githubRequest(
    `/repos/${repo}/commits?path=${encodeURIComponent(path)}&per_page=${per_page}`
  );

  const result = (commits as Array<Record<string, unknown>>).map((c) => {
    const commit = c.commit as Record<string, unknown>;
    const author = commit?.author as Record<string, unknown> | undefined;
    return {
      sha: (c.sha as string).slice(0, 8),
      message: ((commit?.message as string) ?? "").split("\n")[0],
      author: author?.name ?? "unknown",
      date: author?.date ?? "",
    };
  });

  return JSON.stringify(result, null, 2);
}
