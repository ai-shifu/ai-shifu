const token = process.env.REACT_APP_TOKEN;
const apiUrl = `https://test-api-sifu.agiclass.cn/api/study/run?token=${token}`;

export const Run = (data, options, oldCOntent = '') => {
  let xtextContent = '';
  EventSource = window?.SSE;
  const evtSource = new EventSource(apiUrl, {
    // @ts-ignore
    headers: {
      Authorization: 'Bearer ' + window.localStorage.getItem('token'),
      'Content-Type': 'application/json',
    },
    methods: 'POST',
    payload: JSON.stringify(data),
  });

  evtSource.onopen = function () {};

  evtSource.onmessage = async function (e) {
    const data = JSON.parse(e?.data || '{}');
    xtextContent += data?.content;
    options?.onMessage({
      message: xtextContent,
      status: 'pending',
    });
    if (data?.type === 'text_end') {
      options?.onEnd({
        message: xtextContent,
        status: 'done',
      });
      evtSource.close();
    }
  };

  evtSource.onerror = async function () {};

  evtSource.stream();

  const close = () => {
    evtSource.close();
  };
  return {
    close,
  };
};
