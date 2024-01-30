# Research Commands

> In what follows, _KB_ stands for _knowledge base_, also known as a document _collection_.

Here are the most important commands you can use for Internet research:

- `/research <your query>`: start new Internet research, generate report, create KB from fetched sites
- `/research deeper`: expand report and KB to cover 2x more sites as current report
- `/research deeper 3`: perform the above 3 times (careful - time/number of steps increases exponentially)

You can also use the following commands:

- `/research new <your query>`: same as without `new` (can use if the first word looks like a command)
- `/research more`: keep original query, but fetch more websites and create new report version
- `/research combine`: combine reports to get a report that takes more sources into account
- `/research auto 42`: performs 42 iterationso of "more"/"combine"
- `/research iterate`: fetch more websites and iterate on the previous report
- `/research <cmd> 42`: repeat command such as `more`, `combine`, etc. 42 times

You can also view the reports:

- `/research view main`: view the main report (`main` can be omitted)
- `/research view stats`: view just the report stats
- `/research view base`: view the base reports
- `/research view combined`: view the combined reports

## Appendix

Let's go over the commands in more detail to get a better understanding of what they do and the differences between them.

### The `iterate` subcommand

If you type `/research iterate`, DocDocGo will fetch more content from the web and use it to try to improve the report. If you type `/research iterate N`, DocDocGo will automatically do `N` repetitions of the `/research iterate` command. Each repetition will fetch more content related to your original query and produce a new version of the report. All fetched content will be added to a KB (aka _collection_) for any follow-up questions.

> If you are doing multiple iterations and want to abort, simply reload the app.

### The `deeper` subcommand

The above approach sound neat, but it doesn't always work in practice, especially if you use a not-so-smart model, like GPT-3.5. Specifically, it sometimes treats the information from the latest small batch of sources on an equal or higher footing than the information in the pre-existing report, even when the latter is based on many more sources and thus should be prioritized. Important information can then be lost and the report can become worse, not better.

That's why we have the `/research deeper` command. Instead of using new sources to try to directly improve the report, it uses a combination of `more` and `combine` operations to generate _separate_ reports from additional sources and then combine them with the existing report(s) in a way that doesn't unfairly prioritize the new sources. Each run of the `/research deeper` command will double the number of sources in the report.

> As always, all fetched content will be added to the collection for any follow-up chat.

### "Infinite" research

The "infinite" research capability of DocDocGo comes from the ability to automatically perform multiple repetitions of the `deeper` command (and other research commands). Simply run `/research deeper N`, where `N` is a number, to automatically run the `deeper` command `N` times, each time doubling the number of sources. Setting `N` to 5, for example, will result in a report that is based on 32x more sources than the initial report (around 200). This will take a while, of course, and you can abort at any time by reloading the app.

### The `more` and `combine` subcommands

What are these `more` and `combine` operations? `/research more` allows you to fetch more content from the web and generate a _separate_ report, without affecting the original report. This is useful if you want to see what else is out there, but don't want to risk messing up the original report.

Such separate reports are called _base reports_. If you'd like to combine the most important information from two base reports into one report, you can use the `/research combine` command. It will automatically find the two highest-level reports (at the same level) that haven't been combined yet and combine them. "Level" here roughly corresponds to the number of sources that went into the report. More precisely, base reports have level 0. When two reports are combined, the level of the new report is 1 higher than the level of the two reports that were combined.

### The `auto` subcommand

The `/research auto` command is a combination of the `/research more` and `/research combine` commands. It automatically selects one or the other. If there are reports to combine, it will use the `/research combine` command. Otherwise, it will use the `/research more` command to fetch more content from the web and generate a new base report.

You can request multiple iterations of this command. For example, `/research auto 42` will automatically perform 42 iterations of `/research auto`. (To abort, simply reload the app.)

You can add a number to the end of the `/research more` and `/research combine` commands as well to repeat them multiple times.

### The relationship between the `auto` and `deeper` commands

Both of these commands can be used to perform "infinite" research, but the `deeper` command is more user-friendly because most values for the number of `auto` iterations will result in a final output that may cause confusion.

For example, after performing the initial research, running `/research auto 2` will perform one iteration of `more` and one iteration of `combine`. This will result in a report that is based on 2x more sources than the original report. Running `/research auto 3`, however, will perform the two iterations above, plus an additional `more` step. As a result, there will be 3 base reports and 1 combined report, and the final output will be the 3rd base report. While you can still view the combined report by scrolling up or by running `/re view`, this state of affairs is likely to be confusing.

Only certain specific values for the number of `auto` iterations will result in a final output that is a report based on combining all of the previous reports. After doing a bit of math, you can convince yourself that if you only have one base report, then `/research auto 2^N - 2` will result in a report based on 2^(N-1) sources.

But of course, you don't want to have to do math to figure out how many iterations to run. That's why the `deeper` command is more user-friendly. It will automatically figure out how many iterations to run to get a report based on 2x more sources than the current main report.

### The `view` subcommand

Finally, you can view the reports and some stats on them using the `/research view` command. The `/research view stats` command will show the report stats, such as how many sources have been processed, how many base and combined reports there are, etc. The `/research view main` command (`main` is optional) will show the stats and main report, i.e. the report that combines the most sources. The `/research view base` command will show the base reports. The `/research view combined` command will show the combined reports.
