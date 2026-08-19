import type { RunMeta } from "./types";

type CiMeta = Pick<RunMeta, "ci_provider" | "branch" | "commit_sha" | "build_url">;

/**
 * Branch, commit and a link back to the build, read from whatever the CI
 * provider exported. This is the difference between a run row that says
 * "checkout.spec.ts failed" and one you can click through to the pipeline
 * that produced it - and it costs the user nothing to configure.
 */
export function detectCi(env: NodeJS.ProcessEnv = process.env): CiMeta {
  if (env.GITHUB_ACTIONS) {
    const server = env.GITHUB_SERVER_URL || "https://github.com";
    return {
      ci_provider: "github-actions",
      branch: env.GITHUB_HEAD_REF || env.GITHUB_REF_NAME,
      commit_sha: env.GITHUB_SHA,
      build_url:
        env.GITHUB_RUN_ID && env.GITHUB_REPOSITORY
          ? `${server}/${env.GITHUB_REPOSITORY}/actions/runs/${env.GITHUB_RUN_ID}`
          : undefined,
    };
  }
  if (env.GITLAB_CI) {
    return {
      ci_provider: "gitlab",
      branch: env.CI_COMMIT_REF_NAME,
      commit_sha: env.CI_COMMIT_SHA,
      build_url: env.CI_PIPELINE_URL || env.CI_JOB_URL,
    };
  }
  if (env.JENKINS_URL) {
    return {
      ci_provider: "jenkins",
      branch: env.BRANCH_NAME || env.GIT_BRANCH,
      commit_sha: env.GIT_COMMIT,
      build_url: env.BUILD_URL,
    };
  }
  if (env.TF_BUILD) {
    const collection = env.SYSTEM_TEAMFOUNDATIONCOLLECTIONURI;
    const project = env.SYSTEM_TEAMPROJECT;
    const buildId = env.BUILD_BUILDID;
    return {
      ci_provider: "azure-devops",
      branch: env.BUILD_SOURCEBRANCHNAME,
      commit_sha: env.BUILD_SOURCEVERSION,
      build_url:
        collection && project && buildId
          ? `${collection}${encodeURIComponent(project)}/_build/results?buildId=${buildId}`
          : collection,
    };
  }
  if (env.BITBUCKET_BUILD_NUMBER) {
    const repo = env.BITBUCKET_REPO_FULL_NAME;
    return {
      ci_provider: "bitbucket",
      branch: env.BITBUCKET_BRANCH,
      commit_sha: env.BITBUCKET_COMMIT,
      build_url: repo
        ? `https://bitbucket.org/${repo}/pipelines/results/${env.BITBUCKET_BUILD_NUMBER}`
        : undefined,
    };
  }
  if (env.CIRCLECI) {
    return {
      ci_provider: "circleci",
      branch: env.CIRCLE_BRANCH,
      commit_sha: env.CIRCLE_SHA1,
      build_url: env.CIRCLE_BUILD_URL,
    };
  }
  return {};
}
