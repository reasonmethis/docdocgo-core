# Research Commands

You can use the following commands for research tasks:

- `/research <your query>`: start new Internet research, generate a report, and ingest fetched sites
- `/research new <your query>`: same as above
- `/research more`: keep original query, but fetch more websites and create a new report version
- `/research combine`: combine reports to get a report that takes more sources into account
- `/research auto 42`: performs 42 iterationso of "more"/"combine"
- `/research iterate`: fetch more websites and iterate on the previous report
- `/research <cmd> 42`: repeat command such as `more`, `combine`, etc. 42 times

You can also view the reports:

- `/research view main`: view the main report (`main` can be omitted)
- `/research view base`: view the base reports
- `/research view combined`: view the combined reports

## Appendix

Let's go over the commands in more detail.

If you type `/research iterate`, DocDocGo will fetch more content from the web and use it to try to improve the report. If you type `/research iterate N`, DocDocGo will automatically do `N` repetitions of the `/research iterate` command. Each repetition will fetch more content related to your original query and produce a new version of the report.

If you are doing multiple iterations and want to abort, simply reload the app.

The above approach sound neat, but it doesn't always work in practice, especially if you use a not-so-smart model, like GPT-3.5. That's why we have the `/research more` command. It allows you to fetch more content from the web and generate a _separate_ report, without affecting the original report. This is useful if you want to see what else is out there, but don't want to risk messing up the original report.

Such separate reports are called _base reports_. If you'd like to combine two base reports into one "super" report, you can use the `/research combine` command.

The `/research auto` command is a combination of the `/research more` and `/research combine` commands. It automatically selects one or the other. If there are reports to combine, it will use the `/research combine` command. Otherwise, it will use the `/research more` command to fetch more content from the web and generate a new base report.

The "infinite" research capability comes from the ability to add a number to the end. For example, `/research auto 42` will automatically 42 iterations of the `/research auto` command. (To abort, simply reload the app.)

You can add a number to the end of the `/research more` and `/research combine` commands a well to repeat them multiple times.

Finally, you can view the reports and some stats on them using the `/research view` command. The `/research view main` command will show the main report, i.e. the report that combines the most sources. The `/research view base` command will show the base reports. The `/research view combined` command will show the combined reports.
