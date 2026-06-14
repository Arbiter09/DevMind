import { z } from "zod";
import { githubRequest } from "../github.js";

export const getPrMetadataSchema = z.object({
  pr_number: z.number().int().positive().describe("Pull request number"),
  repo: z.string().describe("Repository in owner/repo format"),
});

export const getPrDiffSchema = z.object({
  pr_number: z.number().int().positive().describe("Pull request number"),
  repo: z.string().describe("Repository in owner/repo format"),
});

export const listChangedFilesSchema = z.object({
  pr_number: z.number().int().positive().describe("Pull request number"),
  repo: z.string().describe("Repository in owner/repo format"),
});

export async function getPrMetadata(args: z.infer<typeof getPrMetadataSchema>): Promise<string> {
  const { pr_number, repo } = args;
  const data = await githubRequest(`/repos/${repo}/pulls/${pr_number}`) as Record<string, unknown>;
  const user = data.user as Record<string, unknown> | undefined;
  const base = data.base as Record<string, unknown> | undefined;
  const head = data.head as Record<string, unknown> | undefined;
  const labels = (data.labels as Array<{ name: string }> | undefined) ?? [];
  const result = {
    number: data.number,
    title: data.title,
    author: user?.login ?? "unknown",
    state: data.state,
    draft: data.draft ?? false,
    base_branch: (base?.ref as string | undefined) ?? "main",
    head_branch: (head?.ref as string | undefined) ?? "",
    head_sha: (head?.sha as string | undefined) ?? "",
    base_sha: (base?.sha as string | undefined) ?? "",
    labels: labels.map((l) => l.name),
    additions: data.additions ?? 0,
    deletions: data.deletions ?? 0,
    changed_files: data.changed_files ?? 0,
    body: data.body ?? "",
    created_at: data.created_at,
    updated_at: data.updated_at,
  };
  return JSON.stringify(result, null, 2);
}

export async function getPrDiff(args: z.infer<typeof getPrDiffSchema>): Promise<string> {
  const { pr_number, repo } = args;
  const diff = await githubRequest(
    `/repos/${repo}/pulls/${pr_number}`,
    { accept: "application/vnd.github.v3.diff" }
  );
  return typeof diff === "string" ? diff : JSON.stringify(diff);
}

export async function listChangedFiles(
  args: z.infer<typeof listChangedFilesSchema>
): Promise<string> {
  const { pr_number, repo } = args;
  const files = await githubRequest(`/repos/${repo}/pulls/${pr_number}/files`);
  const result = (files as Array<Record<string, unknown>>).map((f) => ({
    filename: f.filename,
    status: f.status,
    additions: f.additions ?? 0,
    deletions: f.deletions ?? 0,
    changes: f.changes ?? 0,
    patch: (f.patch as string | undefined)?.slice(0, 2000) ?? "",
  }));
  return JSON.stringify(result, null, 2);
}
