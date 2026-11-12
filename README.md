# goodboy

**Throw it a task. It fetches the skill from GitHub.**

goodboy is a command-line tool that searches GitHub live for the **most-starred repos that provide a skill for your task**, picks the best skill among them, and fetches it. A skill is a folder with a `SKILL.md` (instructions, plus optional scripts and references) for one kind of job, like PDFs, MCP servers or port-scan triage. The deciding is done by a small model **trained for this one job**. There's no LLM, no API key and no GPU, and a lookup takes about 0.1 s.

```
$ goodboy fetch "i need a design skill for my landing page"
Searched GitHub for: design landing page skill
Top 3 repos by stars that have a matching skill:
  148.4k stars  nextlevelbuilder/ui-ux-pro-max-skill  (7 skills)
   53.6k stars  Nutlope/hallmark  (1 skill)
   15.3k stars  elayadesign/ai-design-skills  (2 skills)

Fetched: elayadesign/ai-design-skills:landing-page-design  (confidence 100%)
Saved to: ~/.local/share/goodboy/skills/elayadesign__ai-design-skills/landing-page-design
...the most relevant sections of the skill...

$ goodboy fetch "review my python code for security vulnerabilities"
Top 1 repos by stars that have a matching skill:
   70.6k stars  cloudflare/security-audit-skill  (1 skill)
Fetched: cloudflare/security-audit-skill:security-audit  (confidence 100%)
```

## Install

```bash
git clone https://github.com/Mamdouhelzein/goodboy && cd goodboy
pipx install .          # or: pip install --user .
```

Needs Python 3.9+ and `git`. Runtime dependencies are just `numpy` and `PyYAML`.

## Usage

| Command | What it does |
|---|---|
| `goodboy` | Interactive mode: type requests at a `fetch>` prompt. |
| `goodboy fetch "<task>"` | Search GitHub, pick the skill, download it, show the most relevant sections. `--full` prints everything. |
| `goodboy search "<task>"` | Show the ranking with confidence, without downloading. |
| `goodboy get owner/repo:skill` | Fetch one specific skill from GitHub (or a saved-source skill by name). |
| `goodboy list [--installed]` | Everything indexed, or what you've fetched. |
| `goodboy sources [add\|remove] <repo>` | Choose which GitHub repos it fetches from. |
| `goodboy refresh` | Re-pull all sources. |
| `goodboy model` | Show the trained model's evaluation numbers. |

### Saved sources (`--local`)

`fetch` and `search` take `--local` to skip the live search and use only your saved sources, which also works offline. Saved sources default to [`anthropics/skills`](https://github.com/anthropics/skills) and from this repo's own [`skills/`](skills) folder, which has 20 skills with a security focus: nmap triage, log analysis, phishing, leaked secrets, Docker and Linux hardening, JWTs, pcaps, CTF crypto and more.

```bash
goodboy sources add someuser/their-skills             # a whole repo
goodboy sources add someuser/monorepo/agent-skills    # one folder of it
goodboy sources add someuser/their-skills@dev         # a branch or tag
goodboy sources add ~/my-skills                       # a local folder
```

## How the GitHub search works

1. **Keywords.** Your request is cut down to its topic words: "i need a design skill for my landing page" becomes `design landing page`.
2. **Search.** GitHub repo search runs for `design landing page skill`, then for each word alone, sorted by stars.
3. **Verify.** In star order, each repo gets a *tree-only* clone (file names, no contents) to check for real `SKILL.md` files. Up to 12 repos are checked, and only their SKILL.md files are downloaded.
4. **Relevance.** The trained model ranks every skill found. A repo counts as providing the skill if one of its skills is in the overall top 10 and covers your request.
5. **Top 3 by stars.** The 3 most-starred matching repos are chosen. The repo with the single best match always gets a slot, so popularity can't push the right skill out.
6. **Fetch.** The best skill among those 3 is chosen, and only *that skill's folder* is checked out.

Results are cached for a day, so repeat requests take about half a second; the first search for a topic takes 20–30 s. Unauthenticated GitHub search allows about 10 searches a minute, so set `GITHUB_TOKEN` if you hit the limit.

## The model

### What it learns

Most skill routers either match keywords or ask a big LLM. goodboy trains a small **learning-to-rank** model instead.

For a request *q* and every skill *s*, it computes 25 features describing how well they match:

- BM25 and TF-IDF scores against the skill's name, description and instructions
- character n-gram similarity, which catches typos and word forms
- how much of the request each field covers
- query-level signals, such as how well the request matches *any* skill and the gap to the runner-up

A model trained on labelled requests turns those features into P(*s* is the skill you need). If the best skill doesn't clear a learned confidence threshold, goodboy doesn't fetch anything. That's how it ignores small talk.

Because the model scores **request–skill pairs** rather than picking from a fixed list of classes, it **works on skills it has never seen**. Add any repo and it routes to those skills too, with no retraining.

### How it's evaluated

Training uses 39 skills and 315 hand-written requests, 50 of which need no skill. Evaluation is 5-fold cross-validation **grouped by skill**: in each fold, the test requests belong to skills whose requests were never used in training. That's the realistic case of adding a new repo.

| Model | top-1 | top-3 | MRR |
|---|---|---|---|
| **goodboy (logistic regression over ranking features)** | **90.2%** | **97.0%** | **0.937** |
| small neural net (32-16 MLP), same features | 87.5% | 93.6% | 0.912 |
| BM25 over descriptions (baseline) | 85.7% | 93.2% | 0.899 |
| keyword scoring (v0.1 baseline) | 74.7% | 88.3% | 0.827 |

With the confidence threshold, **routing accuracy is 88.9%**: it either fetches the right skill, or correctly fetches nothing for small talk. The baselines can't abstain at all. The neural net lost to logistic regression, so the simpler model ships.

The weights are stored as plain JSON in `goodboy/router.json` (2 KB, no pickles), and inference is a few lines of numpy.

### Known limits

- **Vague or niche requests.** For something vague ("add security to my code"), the most-starred results are giant collections with hundreds of skills, and goodboy often isn't confident enough to pick one. For niche topics with few starred skills on GitHub (nmap is one), the live search can pull in unrelated repos. Use specific wording, or `--local` with a source that covers the topic.
- **Synonyms.** It matches words, so "flyer" doesn't connect to a skill that only says "poster". Requests that share one stray word with a skill ("favorite *color*" → brand-guidelines) can also fool it. Pretrained word embeddings would be the next step.
- **Borderline requests.** When it isn't confident enough, it lists its best guesses and the matching `goodboy get` commands instead of fetching.

### Retrain it

```bash
pip install -e '.[train]'
# add lines to training/data/queries.yaml (and skills to skills/), then:
python training/train.py      # prints the evaluation, writes goodboy/router.json
```

## Security

Skills are third-party content:

- Live search pulls from **any public repo** that ranks on GitHub, so treat fetched skills like code from a stranger.
- goodboy **never runs anything**. It copies files and prints instructions, and it flags when a skill contains scripts so you read them first.
- Symlinks in skill repos are never copied, file reads are confined to the skill folder, and size caps apply.
- Sources are fetched with shallow `git clone`, which avoids GitHub API rate limits. Only add repos you'd trust enough to read.

## Development

```bash
pip install -e '.[dev]' && pytest
```

## License

MIT
