import req from './request'

export const listSubscriptions = () => req.get('/subscriptions')
export const toggleSubscription = (metric, subscribed) =>
  req.patch(`/subscriptions/${metric}`, { subscribed })
