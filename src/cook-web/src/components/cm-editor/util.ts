import {
  type CompletionContext,
  type CompletionResult
} from '@codemirror/autocomplete'
import {
  EditorView,
  Decoration,
  DecorationSet,
  ViewPlugin,
  ViewUpdate,
  MatchDecorator,
  WidgetType
} from '@codemirror/view'
import { SelectedOption } from './type'
import './index.css'
import { biliVideoUrlRegexp } from '@/components/cm-editor/components/video-inject'
import { getI18n } from 'react-i18next'

const profileRegexp = /<span\s+data-tag="profile"[^>]*>\{(\w+)\}<\/span>/gi
const biliVideoContextRegexp =
  /<span\s+data-tag="video"[^>]*data-url="([^"]+)"[^>]*data-title="([^"]+)"[^>]*>([^<]+)<\/span>/gi
const agiImgContextRegexp =
  /<span\s+data-tag="image"[^>]*data-url="([^"]*)"[^>]*data-title="([^"]*)"[^>]*data-scale="([^"]*)"[^>]*>([^<]+)<\/span>/gi

// get value from content
const parseContentInfo = (
  type: SelectedOption,
  dataset: { title: string; url: string; scale: string }
) => {
  switch (type) {
    case SelectedOption.Profile:
      return dataset.title
    case SelectedOption.Image:
      return {
        resourceUrl: dataset.url,
        resourceTitle: dataset.title,
        resourceScale: dataset.scale
      }

    case SelectedOption.Video:
      return {
        resourceUrl: dataset.url,
        resourceTitle: dataset.title
      }
  }
}

class PlaceholderWidget extends WidgetType {
  constructor (
    private text: string,
    private dataset: any,
    private styleClass: string,
    private type: SelectedOption,
    private view: EditorView
  ) {
    super()
  }

  getPosition () {
    let from = -1
    let to = -1
    const decorations = this.view.state.facet(EditorView.decorations)
    for (const deco of decorations) {
      const decoSet = typeof deco === 'function' ? deco(this.view) : deco
      decoSet.between(
        0,
        this.view.state.doc.length,
        (start: number, end: number, decoration: Decoration) => {
          if (decoration.spec.widget === this) {
            from = start
            to = end
            return false
          }
        }
      )
      if (from !== -1) break
    }
    if (from !== -1 && to !== -1) {
      return [from, to]
    }
  }

  toDOM () {
    const container = document.createElement('span')
    container.className = this.styleClass
    const span = document.createElement('span')
    span.textContent = this.text
    span.dataset['tag'] = this.dataset.tag || ''
    span.dataset['url'] = this.dataset.url || ''
    span.dataset['title'] = this.dataset.title || ''
    const icon = document.createElement('span')
    icon.className = 'tag-icon'
    icon.innerHTML = '✕'
    icon.addEventListener('click', e => {
      e.stopPropagation()
      const [from, to] = this.getPosition() ?? [-1, -1]
      if (from !== -1 && to !== -1) {
        this.view.dispatch({
          changes: { from, to, insert: '' }
        })
      }
    })
    span.addEventListener('click', () => {
      const [from, to] = this.getPosition() ?? [-1, -1]
      const event = new CustomEvent('globalTagClick', {
        detail: {
          view: this.view,
          type: this.type,
          dataset: this.dataset,
          content:
            this.type === SelectedOption.Profile
              ? span.textContent?.replace(/[{}]/g, '')
              : span.textContent,
          from,
          to
        }
      })
      window.dispatchEvent(event)
    })
    container.appendChild(span)
    container.appendChild(icon)
    return container
  }

  ignoreEvent () {
    return false
  }
}

const profileMatcher = new MatchDecorator({
  regexp: profileRegexp,
  decoration: (match, view) =>
    Decoration.replace({
      widget: new PlaceholderWidget(
        match[1],
        {
          tag: 'profile',
          title: match[1]
        },
        'tag-profile',
        SelectedOption.Profile,
        view
      )
    })
})

const imageUrlMatcher = new MatchDecorator({
  regexp: agiImgContextRegexp,
  decoration: (match, view) =>
    Decoration.replace({
      widget: new PlaceholderWidget(
        match?.[4],
        {
          tag: 'image',
          url: match?.[1],
          title: match?.[2],
          scale: match?.[3]
        },
        'tag-image',
        SelectedOption.Image,
        view
      )
    })
})

const biliUrlMatcher = new MatchDecorator({
  regexp: biliVideoContextRegexp,
  decoration: (match, view) =>
    Decoration.replace({
      widget: new PlaceholderWidget(
        match?.[3],
        {
          tag: 'video',
          url: match?.[1],
          title: match?.[2]
        },
        'tag-video',
        SelectedOption.Video,
        view
      )
    })
})

const variablePlaceholders = ViewPlugin.fromClass(
  class {
    placeholders: DecorationSet
    constructor (view: EditorView) {
      this.placeholders = profileMatcher.createDeco(view)
    }
    update (update: ViewUpdate) {
      this.placeholders = profileMatcher.updateDeco(update, this.placeholders)
    }
  },
  {
    decorations: instance => instance.placeholders,
    provide: plugin =>
      EditorView.atomicRanges.of(view => {
        return view.plugin(plugin)?.placeholders || Decoration.none
      })
  }
)

const imgPlaceholders = ViewPlugin.fromClass(
  class {
    placeholders: DecorationSet
    constructor (view: EditorView) {
      this.placeholders = imageUrlMatcher.createDeco(view)
    }
    update (update: ViewUpdate) {
      this.placeholders = imageUrlMatcher.updateDeco(update, this.placeholders)
    }
  },
  {
    decorations: instance => instance.placeholders,
    provide: plugin =>
      EditorView.atomicRanges.of(view => {
        return view.plugin(plugin)?.placeholders || Decoration.none
      })
  }
)

const videoPlaceholders = ViewPlugin.fromClass(
  class {
    placeholders: DecorationSet
    constructor (view: EditorView) {
      this.placeholders = biliUrlMatcher.createDeco(view)
    }
    update (update: ViewUpdate) {
      this.placeholders = biliUrlMatcher.updateDeco(update, this.placeholders)
    }
  },
  {
    decorations: instance => instance.placeholders,
    provide: plugin =>
      EditorView.atomicRanges.of(view => {
        return view.plugin(plugin)?.placeholders || Decoration.none
      })
  }
)

function createSlashCommands (
  onSelectOption: (selectedOption: SelectedOption) => void
) {
  const t = getI18n()?.t
  return (context: CompletionContext): CompletionResult | null => {
    const word = context.matchBefore(/\/(\w*)$/)
    if (!word) return null

    const handleSelect = (
      view: EditorView,
      _: any,
      from: number,
      to: number,
      selectedOption: SelectedOption
    ) => {
      view.dispatch({
        changes: { from, to, insert: '' }
      })
      onSelectOption(selectedOption)
    }

    return {
      from: word.from,
      to: word.to,
      options: [
        {
          label: t('cm-editor.variable'),
          apply: (view, _, from, to) => {
            handleSelect(view, _, from, to, SelectedOption.Profile)
          }
        },
        {
          label: t('cm-editor.image'),
          apply: (view, _, from, to) => {
            handleSelect(view, _, from, to, SelectedOption.Image)
          }
        },
        {
          label: t('cm-editor.video'),
          apply: (view, _, from, to) => {
            handleSelect(view, _, from, to, SelectedOption.Video)
          }
        }
      ],
      filter: false
    }
  }
}

export {
  biliVideoUrlRegexp,
  profileRegexp,
  variablePlaceholders,
  imgPlaceholders,
  videoPlaceholders,
  createSlashCommands,
  parseContentInfo
}
