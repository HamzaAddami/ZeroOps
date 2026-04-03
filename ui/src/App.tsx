import { useState } from 'react'
import axios from 'axios'
function App() {
  
  const [data, setData] = useState(null)

  const fetchData = async () => {
    try {
      const response = (await axios.get('http://127.0.0.1:8000/health'))
      setData(response.data)
      alert('Server is healthy!')
    }
    catch (error) {
      console.error('Error fetching data:', error)
    }
  }



  return (
    <>
      <button onClick={fetchData}>Check Server</button>
      {data && <pre>{JSON.stringify(data, null, 2)}</pre>}
    </>
  )
}

export default App
