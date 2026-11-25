import { useEffect, useRef } from 'react';
import { EditorState, StateEffect, StateField, RangeSetBuilder } from '@codemirror/state';
import { Decoration, EditorView, keymap, lineNumbers, highlightActiveLine, drawSelection, type DecorationSet } from '@codemirror/view';
import { defaultKeymap, history, historyKeymap, indentWithTab } from '@codemirror/commands';
import { python } from '@codemirror/lang-python';
import { cpp } from '@codemirror/lang-cpp';
import type { Lang } from '../content/types';
import { bracketMatching, indentUnit, syntaxHighlighting, HighlightStyle } from '@codemirror/language';
import { tags as t } from '@lezer/highlight';

const style = HighlightStyle.define([
  { tag: [t.keyword, t.controlKeyword, t.definitionKeyword, t.operatorKeyword, t.bool, t.null], color: 'var(--kw)', fontWeight: '600' },
  { tag: [t.string, t.special(t.string)], color: 'var(--str)' },
  { tag: [t.number], color: 'var(--num)' },
  { tag: [t.comment, t.lineComment], color: 'var(--com)', fontStyle: 'italic' },
  { tag: [t.function(t.variableName), t.function(t.propertyName), t.standard(t.variableName)], color: 'var(--fn)' },
]);

const theme = EditorView.theme({
  '&': { backgroundColor: 'var(--code-bg)', color: 'var(--code-ink)' },
  '.cm-content': { caretColor: 'var(--ink)', padding: '0.5rem 0' },
  '.cm-cursor': { borderLeftColor: 'var(--ink)' },
  '&.cm-focused .cm-selectionBackground, .cm-selectionBackground, ::selection': { backgroundColor: 'color-mix(in srgb, var(--accent) 25%, transparent)' },
  '.cm-activeLine': { backgroundColor: 'color-mix(in srgb, var(--accent) 7%, transparent)' },
});

const setChanged = StateEffect.define<number[]>();
const changedField = StateField.define<DecorationSet>({
  create: () => Decoration.none,
  update(deco, tr) {
    for (const e of tr.effects) {
      if (e.is(setChanged)) {
        const b = new RangeSetBuilder<Decoration>();
        const doc = tr.state.doc;
        for (const n of [...e.value].sort((x, y) => x - y)) {
          if (n >= 1 && n <= doc.lines) b.add(doc.line(n).from, doc.line(n).from, Decoration.line({ class: 'cm-changed' }));
        }
        return b.finish();
      }
    }
    return tr.docChanged ? deco.map(tr.changes) : deco;
  },
  provide: (f) => EditorView.decorations.from(f),
});

interface Props {
  value: string;
  onChange: (v: string) => void;
  /** 처음 코드와 다른 줄(1부터): 노란 배경 */
  changedLines?: number[];
  label: string;
  lang?: Lang;
}

/** 코드 편집기(CodeMirror, 파이썬·C). Tab = 들여쓰기(Esc 다음 Tab으로 빠져나감). */
export function CodeEditor({ value, onChange, changedLines, label, lang = 'python' }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const view = useRef<EditorView | null>(null);
  const cb = useRef(onChange);
  cb.current = onChange;

  useEffect(() => {
    const v = new EditorView({
      parent: host.current!,
      state: EditorState.create({
        doc: value,
        extensions: [
          lineNumbers(),
          history(),
          drawSelection(),
          highlightActiveLine(),
          bracketMatching(),
          indentUnit.of('    '),
          EditorState.tabSize.of(4),
          lang === 'c' ? cpp() : python(),
          syntaxHighlighting(style),
          theme,
          changedField,
          keymap.of([indentWithTab, ...defaultKeymap, ...historyKeymap]),
          EditorView.contentAttributes.of({ 'aria-label': label, autocapitalize: 'off', autocorrect: 'off', spellcheck: 'false' }),
          EditorView.updateListener.of((u) => {
            if (u.docChanged) cb.current(u.state.doc.toString());
          }),
        ],
      }),
    });
    view.current = v;
    return () => {
      v.destroy();
      view.current = null;
    };
    // 처음 한 번만 만든다(값 바꾸기는 아래 효과)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 밖에서 값이 바뀌면(초기화 등) 편집기에 반영
  useEffect(() => {
    const v = view.current;
    if (v && v.state.doc.toString() !== value) v.dispatch({ changes: { from: 0, to: v.state.doc.length, insert: value } });
  }, [value]);

  useEffect(() => {
    view.current?.dispatch({ effects: setChanged.of(changedLines ?? []) });
  }, [changedLines]);

  return <div className="cm-host code-box" ref={host} />;
}
