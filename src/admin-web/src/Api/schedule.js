import request from "../Service/Request";

export const GetAllSchedules = async (start, endtime) => {
  if (start != null && endtime != null) {
    return request({
      url: "/api/schedule/all?start=" + start + "&end=" + endtime,
      method: "get",
    });
  }
  return request({
    url: "/api/schedule/all",
    method: "get",
  });
};
export const CreateSchedule = async (data) => {
  return request({
    url: "/api/schedule/create",
    method: "post",
    data: data,
  });
};

/**
 *
 * @param {*} data
 * @returns
 *
 *      schedule_id = request.get_json().get('schedule_id', '')
        description = request.get_json().get('description', '')
        datetime = request.get_json().get('datetime', '')
        endtime = request.get_json().get('endtime', '')
        location = request.get_json().get('location', '')
        participants = request.get_json().get('participants', '')
        details = request.get_json().get('details', '')
 */
export const UpdateSchedule = async (data) => {
  return request({
    url: "/api/schedule/update",
    method: "post",
    data: data,
  });
};

export const GetScheduleDetails = async (id) => {
  return request({
    url: "/api/schedule/detail?schedule_id=" + id,
    method: "get",
  });
};

/**
 * @description 删除日程
 * @param {*} schedule_id 日程 ID
 * @returns
 */
export const DeleteSchedule = async (schedule_id) => {
  return request({
    url: "/api/schedule/delete",
    method: "post",
    data: { schedule_id },
  });
};
