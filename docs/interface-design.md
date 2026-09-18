# Interface design

Frontier Research is a local study desk: the broad equity canvas is the primary object, with a narrow, aligned setup column that reads like a lab protocol. The left rail keeps Study, Data, Experiments and Operations available. Dataset evidence stays next to its name; currency and time belong to the plotted axes.

Tokens: paper #F7FAFD; white #FFFFFF; ink #18324B; blue #245BD3; teal #167D8D; amber #9A5A12. Segoe UI/Aptos/system sans; 30/22/16/14/12px scale; tabular numerals for all results. Content left aligned, numeric tables right aligned. 8px spacing rhythm, subtle ruled divisions, 6px control radii, no floating card shadows.

```
rail  | Research study                         service / workspace
      | dataset provenance / observation span
      | Equity / currency                    | Study setup
      |                                      | Dataset
      | broad actual-value plot              | Strategy / costs
      |                                      | Run study
      | return | drawdown | fills | fees     | Assumptions
      | Decision replay / fills / holdings
```

Pre-code critique: a dashboard of identical metric cards would obscure the actual experiment. Revised to a single wide chart sheet with an integrated ruled metric strip and a visibly separate setup margin. No sample line or fabricated number fills an empty state. The distinctive element is the blue analytical canvas and its actual timestamped line; all other chrome is quiet. No marketing hero, decorative feed, external font or animation.

Responsive: setup stacks above results below 1050px; rail becomes horizontal on small screens; financial tables scroll independently. Focus rings and native controls support keyboard use. Ctrl+Enter runs the current study. Previous results remain visible when parameters change. Loading communicates actual synchronous work; failed jobs are retained in Experiments.
